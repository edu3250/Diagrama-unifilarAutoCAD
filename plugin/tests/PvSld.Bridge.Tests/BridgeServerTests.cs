using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json.Nodes;
using PvSld.Bridge;

namespace PvSld.Bridge.Tests;

/// <summary>Handler double: echoes ping, and fails on demand.</summary>
internal sealed class FakeHandler : IBridgeHandler
{
    public int Calls;

    public Task<JsonNode?> HandleAsync(string method, JsonObject? parameters, CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref Calls);
        return method switch
        {
            "ping" => Task.FromResult<JsonNode?>(new JsonObject { ["pong"] = true, ["echo"] = parameters?["echo"]?.DeepClone() }),
            "busy" => throw new BusyException(BusyReasons.CommandActive, "finish the LINE command"),
            "boom" => throw new InvalidOperationException("kaboom"),
            _ => throw new BridgeException(BridgeErrorCodes.MethodNotFound, $"unknown method '{method}'"),
        };
    }
}

public sealed class BridgeServerTests : IAsyncLifetime
{
    private const string Secret = "s3cret-for-tests";
    private readonly FakeHandler _handler = new();
    private readonly string _pipeName = DiscoveryFile.NewPipeName(Environment.ProcessId);
    private BridgeServer _server = null!;

    public Task InitializeAsync()
    {
        _server = new BridgeServer(
            new BridgeServerOptions { PipeName = _pipeName, Secret = Secret, AuthTimeout = TimeSpan.FromMilliseconds(500) },
            _handler);
        _server.Start();
        return Task.CompletedTask;
    }

    public async Task DisposeAsync() => await _server.DisposeAsync();

    private sealed class Client : IAsyncDisposable
    {
        private readonly NamedPipeClientStream _pipe;
        private readonly NdjsonLineReader _reader;
        private int _nextId;

        private Client(NamedPipeClientStream pipe)
        {
            _pipe = pipe;
            _reader = new NdjsonLineReader(pipe);
        }

        public NamedPipeClientStream Pipe => _pipe;

        public static async Task<Client> ConnectAsync(string name)
        {
            var pipe = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous);
            await pipe.ConnectAsync(5000);
            return new Client(pipe);
        }

        public async Task SendRawAsync(string line)
        {
            await _pipe.WriteAsync(Encoding.UTF8.GetBytes(line + "\n"));
            await _pipe.FlushAsync();
        }

        public async Task<JsonObject?> ReceiveAsync()
        {
            var line = await _reader.ReadLineAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(10));
            return line is null ? null : JsonNode.Parse(line)!.AsObject();
        }

        public async Task<JsonObject> CallAsync(string method, JsonObject? parameters = null)
        {
            var request = new JsonObject { ["jsonrpc"] = "2.0", ["id"] = ++_nextId, ["method"] = method };
            if (parameters is not null)
            {
                request["params"] = parameters;
            }

            await SendRawAsync(request.ToJsonString());
            var response = await ReceiveAsync() ?? throw new IOException("connection closed");
            Assert.Equal(_nextId, response["id"]!.GetValue<int>());
            return response;
        }

        public ValueTask DisposeAsync() => _pipe.DisposeAsync();
    }

    private static int ErrorCode(JsonObject response) => response["error"]!["code"]!.GetValue<int>();

    [Fact]
    public async Task Auth_WithSecret_ReturnsServerInfoAndAllowsCalls()
    {
        await using var client = await Client.ConnectAsync(_pipeName);

        var hello = await client.CallAsync("auth", new JsonObject { ["secret"] = Secret });
        var pong = await client.CallAsync("ping", new JsonObject { ["echo"] = "hi" });

        Assert.Equal(BridgeProtocol.Version, hello["result"]!["protocol"]!.GetValue<int>());
        Assert.Contains("batch", hello["result"]!["methods"]!.AsArray().Select(m => m!.GetValue<string>()));
        Assert.Equal("hi", pong["result"]!["echo"]!.GetValue<string>());
    }

    [Fact]
    public async Task Call_WithoutAuth_IsRefusedAndDisconnected()
    {
        await using var client = await Client.ConnectAsync(_pipeName);

        var refused = await client.CallAsync("ping");

        Assert.Equal(BridgeErrorCodes.Unauthorized, ErrorCode(refused));
        Assert.Null(await client.ReceiveAsync()); // server closed the connection
        Assert.Equal(0, _handler.Calls);
        Assert.Equal(1, _server.AuthFailures);
    }

    [Fact]
    public async Task Auth_WithWrongSecret_IsRefused()
    {
        await using var client = await Client.ConnectAsync(_pipeName);

        var refused = await client.CallAsync("auth", new JsonObject { ["secret"] = Secret + "x" });

        Assert.Equal(BridgeErrorCodes.Unauthorized, ErrorCode(refused));
        Assert.Null(await client.ReceiveAsync());
    }

    [Fact]
    public async Task SilentClient_IsDisconnectedAfterAuthTimeout()
    {
        await using var client = await Client.ConnectAsync(_pipeName);

        var timeout = await client.ReceiveAsync();

        Assert.Equal(BridgeErrorCodes.Unauthorized, ErrorCode(timeout!));
        Assert.Null(await client.ReceiveAsync());
    }

    [Fact]
    public async Task HandlerErrors_AreMappedToJsonRpcErrors()
    {
        await using var client = await Client.ConnectAsync(_pipeName);
        await client.CallAsync("auth", new JsonObject { ["secret"] = Secret });

        var busy = await client.CallAsync("busy");
        var boom = await client.CallAsync("boom");
        var unknown = await client.CallAsync("execute_lisp");
        await client.SendRawAsync("{not json");
        var garbage = await client.ReceiveAsync();
        var stillAlive = await client.CallAsync("ping");

        Assert.Equal(BridgeErrorCodes.Busy, ErrorCode(busy));
        Assert.Equal("command_active", busy["error"]!["data"]!["reason"]!.GetValue<string>());
        Assert.Equal(BridgeErrorCodes.InternalError, ErrorCode(boom));
        Assert.Equal(BridgeErrorCodes.MethodNotFound, ErrorCode(unknown));
        Assert.Equal(BridgeErrorCodes.ParseError, ErrorCode(garbage!));
        Assert.True(stillAlive["result"]!["pong"]!.GetValue<bool>());
    }

    [Fact]
    public async Task SeveralClients_AreServedConcurrently()
    {
        var clients = await Task.WhenAll(Enumerable.Range(0, 3).Select(_ => Client.ConnectAsync(_pipeName)));
        try
        {
            foreach (var client in clients)
            {
                await client.CallAsync("auth", new JsonObject { ["secret"] = Secret });
            }

            var pongs = await Task.WhenAll(clients.Select(c => c.CallAsync("ping")));

            Assert.All(pongs, p => Assert.True(p["result"]!["pong"]!.GetValue<bool>()));
        }
        finally
        {
            foreach (var client in clients)
            {
                await client.DisposeAsync();
            }
        }
    }

    [Fact]
    public async Task PipeAcl_OnWindows_AllowsOnlyTheCurrentUserAndDeniesNetwork()
    {
        if (!OperatingSystem.IsWindows())
        {
            return; // CurrentUserOnly is enforced by file permissions on Unix
        }

        await using var client = await Client.ConnectAsync(_pipeName);
        var security = client.Pipe.GetAccessControl();
        var rules = security.GetAccessRules(true, true, typeof(SecurityIdentifier)).Cast<PipeAccessRule>().ToList();
        var user = CurrentUserSecurity.CurrentUser();

        Assert.True(security.AreAccessRulesProtected);
        Assert.Equal(2, rules.Count);
        Assert.Contains(rules, r => r.AccessControlType == AccessControlType.Allow && r.IdentityReference.Equals(user));
        Assert.Contains(rules, r => r.AccessControlType == AccessControlType.Deny
            && r.IdentityReference.Equals(new SecurityIdentifier(WellKnownSidType.NetworkSid, null)));
        Assert.DoesNotContain(rules, r => r.AccessControlType == AccessControlType.Allow && !r.IdentityReference.Equals(user));
    }
}
