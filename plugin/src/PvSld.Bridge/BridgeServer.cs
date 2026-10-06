using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace PvSld.Bridge;

public sealed class BridgeServerOptions
{
    public required string PipeName { get; init; }

    public required string Secret { get; init; }

    /// <summary>Simultaneous client connections (requests still execute one at a time).</summary>
    public int MaxConnections { get; init; } = 4;

    /// <summary>A client that has not authenticated within this time is disconnected.</summary>
    public TimeSpan AuthTimeout { get; init; } = TimeSpan.FromSeconds(5);

    public int MaxLineBytes { get; init; } = BridgeProtocol.MaxLineBytes;

    /// <summary>Server version reported in the auth reply.</summary>
    public string ServerVersion { get; init; } = "0.2.0";
}

/// <summary>
/// Named-pipe JSON-RPC server. Every connection must first send <c>auth</c> with the per-start
/// secret; any other first message, a wrong secret or silence closes the connection.
/// </summary>
public sealed class BridgeServer : IAsyncDisposable
{
    private readonly BridgeServerOptions _options;
    private readonly IBridgeHandler _handler;
    private readonly Action<string> _log;
    private readonly byte[] _secret;
    private readonly SemaphoreSlim _slots;
    private readonly CancellationTokenSource _stop = new();
    private Task? _acceptLoop;
    private long _requests;
    private long _authFailures;
    private int _activeConnections;

    public BridgeServer(BridgeServerOptions options, IBridgeHandler handler, Action<string>? log = null)
    {
        _options = options;
        _handler = handler;
        _log = log ?? (_ => { });
        _secret = Encoding.UTF8.GetBytes(options.Secret);
        _slots = new SemaphoreSlim(options.MaxConnections, options.MaxConnections);
    }

    public string PipeName => _options.PipeName;

    public long RequestsServed => Interlocked.Read(ref _requests);

    public long AuthFailures => Interlocked.Read(ref _authFailures);

    public int ActiveConnections => Volatile.Read(ref _activeConnections);

    public void Start()
    {
        if (_acceptLoop is not null)
        {
            throw new InvalidOperationException("the server is already running");
        }

        // Fail fast on the caller's thread if the pipe cannot be created at all.
        var first = CreatePipe();
        _acceptLoop = Task.Run(() => AcceptLoopAsync(first, _stop.Token));
    }

    public async ValueTask DisposeAsync()
    {
        await _stop.CancelAsync().ConfigureAwait(false);
        if (_acceptLoop is not null)
        {
            try
            {
                await _acceptLoop.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            }
            catch (TimeoutException)
            {
                _log("accept loop did not stop within 5 s");
            }
        }

        _stop.Dispose();
    }

    private NamedPipeServerStream CreatePipe()
    {
        if (OperatingSystem.IsWindows())
        {
            return NamedPipeServerStreamAcl.Create(
                _options.PipeName,
                PipeDirection.InOut,
                _options.MaxConnections,
                PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous,
                inBufferSize: 0,
                outBufferSize: 0,
                CurrentUserSecurity.Pipe());
        }

        return new NamedPipeServerStream(
            _options.PipeName,
            PipeDirection.InOut,
            _options.MaxConnections,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
    }

    private async Task AcceptLoopAsync(NamedPipeServerStream? next, CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            try
            {
                await _slots.WaitAsync(stop).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            var pipe = next;
            next = null;
            try
            {
                pipe ??= CreatePipe();
                await pipe.WaitForConnectionAsync(stop).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                pipe?.Dispose();
                _slots.Release();
                break;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                _log($"pipe accept failed: {ex.Message}");
                pipe?.Dispose();
                _slots.Release();
                await Task.Delay(250, CancellationToken.None).ConfigureAwait(false);
                continue;
            }

            _ = Task.Run(() => ServeConnectionAsync(pipe, stop), CancellationToken.None);
        }

        next?.Dispose();
    }

    private async Task ServeConnectionAsync(NamedPipeServerStream pipe, CancellationToken stop)
    {
        Interlocked.Increment(ref _activeConnections);
        try
        {
            await using (pipe.ConfigureAwait(false))
            {
                await ConverseAsync(pipe, stop).ConfigureAwait(false);
            }
        }
#pragma warning disable CA1031 // A broken connection must never take the listener (or AutoCAD) down.
        catch (Exception ex)
#pragma warning restore CA1031
        {
            _log($"connection ended with {ex.GetType().Name}: {ex.Message}");
        }
        finally
        {
            Interlocked.Decrement(ref _activeConnections);
            _slots.Release();
        }
    }

    private async Task ConverseAsync(Stream pipe, CancellationToken stop)
    {
        var reader = new NdjsonLineReader(pipe, _options.MaxLineBytes);
        var authenticated = false;
        while (!stop.IsCancellationRequested)
        {
            byte[]? line;
            using (var readCancel = CancellationTokenSource.CreateLinkedTokenSource(stop))
            {
                if (!authenticated)
                {
                    readCancel.CancelAfter(_options.AuthTimeout);
                }

                try
                {
                    line = await reader.ReadLineAsync(readCancel.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException) when (!stop.IsCancellationRequested)
                {
                    Interlocked.Increment(ref _authFailures);
                    await SendAsync(pipe, JsonRpc.Error(null, BridgeErrorCodes.Unauthorized, "authentication timed out"), stop)
                        .ConfigureAwait(false);
                    return;
                }
                catch (LineTooLongException ex)
                {
                    await SendAsync(pipe, JsonRpc.Error(null, BridgeErrorCodes.InvalidRequest, ex.Message), stop)
                        .ConfigureAwait(false);
                    return;
                }
            }

            if (line is null)
            {
                return; // client closed the connection
            }

            if (line.Length == 0)
            {
                continue;
            }

            JsonRpcRequest request;
            try
            {
                request = JsonRpc.Parse(line);
            }
            catch (BridgeException ex)
            {
                await SendAsync(pipe, JsonRpc.Error(JsonRpc.TryGetId(line), ex.Code, ex.Message), stop).ConfigureAwait(false);
                if (!authenticated)
                {
                    Interlocked.Increment(ref _authFailures);
                    return;
                }

                continue;
            }

            if (!authenticated || request.Method == BridgeProtocol.Methods.Auth)
            {
                if (request.Method != BridgeProtocol.Methods.Auth || !SecretMatches(request.Params))
                {
                    Interlocked.Increment(ref _authFailures);
                    await SendAsync(
                        pipe,
                        JsonRpc.Error(
                            request.Id,
                            BridgeErrorCodes.Unauthorized,
                            "unauthorized: the first request must be \"auth\" with the secret from the bridge discovery file"),
                        stop).ConfigureAwait(false);
                    return;
                }

                authenticated = true;
                await SendAsync(pipe, JsonRpc.Result(request.Id, Hello()), stop).ConfigureAwait(false);
                continue;
            }

            var response = await DispatchAsync(request, stop).ConfigureAwait(false);
            Interlocked.Increment(ref _requests);
            await SendAsync(pipe, response, stop).ConfigureAwait(false);
        }
    }

    private async Task<string> DispatchAsync(JsonRpcRequest request, CancellationToken stop)
    {
        try
        {
            var result = await _handler.HandleAsync(request.Method, request.Params, stop).ConfigureAwait(false);
            return JsonRpc.Result(request.Id, result);
        }
        catch (BridgeException ex)
        {
            return JsonRpc.Error(request.Id, ex.Code, ex.Message, ex.Data);
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested)
        {
            return JsonRpc.Error(request.Id, BridgeErrorCodes.InternalError, "the bridge is shutting down");
        }
#pragma warning disable CA1031 // Unexpected failures become JSON-RPC internal errors.
        catch (Exception ex)
#pragma warning restore CA1031
        {
            _log($"{request.Method} failed: {ex}");
            return JsonRpc.Error(
                request.Id, BridgeErrorCodes.InternalError, $"internal error: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private JsonObject Hello() => new()
    {
        ["server"] = BridgeProtocol.ServerName,
        ["version"] = _options.ServerVersion,
        ["protocol"] = BridgeProtocol.Version,
        ["methods"] = new JsonArray([.. BridgeProtocol.Methods.All.Select(m => (JsonNode)m)]),
    };

    private bool SecretMatches(JsonObject? parameters)
    {
        if (parameters?["secret"] is not JsonValue value || !value.TryGetValue(out string? secret))
        {
            return false;
        }

        return CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(secret), _secret);
    }

    private static async Task SendAsync(Stream pipe, string json, CancellationToken stop)
    {
        var bytes = Encoding.UTF8.GetBytes(json + "\n");
        await pipe.WriteAsync(bytes, stop).ConfigureAwait(false);
        await pipe.FlushAsync(stop).ConfigureAwait(false);
    }
}
