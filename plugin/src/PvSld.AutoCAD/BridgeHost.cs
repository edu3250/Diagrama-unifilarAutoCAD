using System.Globalization;
using PvSld.Bridge;
using CoreApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace PvSld.AutoCAD;

/// <summary>Wires the pipe server, the main-thread runner and the discovery file for one AutoCAD session.</summary>
internal sealed class BridgeHost : IDisposable
{
    public const string ServerVersion = "0.2.0";

    /// <summary>Longest wait for AutoCAD's main thread before answering "busy" (criterion: 5 s).</summary>
    public static readonly TimeSpan BusyTimeout = TimeSpan.FromSeconds(3);

    /// <summary>Longest a started job may run before the client is told its outcome is unknown.</summary>
    public static readonly TimeSpan ExecutionTimeout = TimeSpan.FromSeconds(60);

    private readonly WinFormsMainThreadScheduler _scheduler;
    private readonly MainThreadJobRunner _runner;
    private readonly BridgeServer _server;
    private readonly FileLog _log;

    private BridgeHost(
        WinFormsMainThreadScheduler scheduler, MainThreadJobRunner runner, BridgeServer server, FileLog log, string discoveryPath)
    {
        _scheduler = scheduler;
        _runner = runner;
        _server = server;
        _log = log;
        DiscoveryPath = discoveryPath;
    }

    public string PipeName => _server.PipeName;

    public string DiscoveryPath { get; }

    /// <summary>Must be called on AutoCAD's main thread (it creates the marshalling window there).</summary>
    public static BridgeHost Start()
    {
        var pid = Environment.ProcessId;
        var directory = DiscoveryFile.DefaultDirectory;
        var log = new FileLog(Path.Combine(directory, $"autocad-{pid}.log"));
        var hostVersion = CoreApp.Version.ToString();
        var scheduler = new WinFormsMainThreadScheduler();
        var runner = new MainThreadJobRunner(scheduler, BusyTimeout, ExecutionTimeout);
        var options = new BridgeServerOptions
        {
            PipeName = DiscoveryFile.NewPipeName(pid),
            Secret = DiscoveryFile.NewSecret(),
            ServerVersion = ServerVersion,
        };
        var handler = new AutoCADBridgeHandler(runner, new HostInfo(pid, hostVersion, ServerVersion));
        var server = new BridgeServer(options, handler, log.Write);
        server.Start();
        var discovery = DiscoveryFile.Write(
            directory,
            new DiscoveryInfo(options.PipeName, options.Secret, pid, $"{BridgeProtocol.ServerName} {ServerVersion}", hostVersion));
        log.Write($"listening on {options.PipeName}; discovery file {discovery}");
        return new BridgeHost(scheduler, runner, server, log, discovery);
    }

    public string Status() => string.Create(
        CultureInfo.InvariantCulture,
        $"pvsld bridge {ServerVersion}: pipe \\\\.\\pipe\\{PipeName}, {_server.ActiveConnections} connection(s), "
        + $"{_server.RequestsServed} request(s), {_server.AuthFailures} refused client(s), "
        + $"{_runner.AbandonedJobs} busy timeout(s); discovery {DiscoveryPath}");

    public void Dispose()
    {
        DiscoveryFile.Delete(DiscoveryPath);
        try
        {
            _server.DisposeAsync().AsTask().Wait(TimeSpan.FromSeconds(2));
        }
        catch (AggregateException ex)
        {
            _log.Write($"stopping the server failed: {ex.InnerException?.Message}");
        }

        _runner.Dispose();
        _scheduler.Dispose();
        _log.Write("stopped");
    }
}

internal sealed record HostInfo(int Pid, string HostVersion, string ServerVersion);

/// <summary>Minimal append-only diagnostics log next to the discovery file.</summary>
internal sealed class FileLog(string path)
{
    private readonly Lock _gate = new();

    public void Write(string message)
    {
        try
        {
            lock (_gate)
            {
                File.AppendAllText(
                    path,
                    $"{DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)} {message}{Environment.NewLine}");
            }
        }
        catch (IOException)
        {
            // Diagnostics must never break the bridge.
        }
        catch (UnauthorizedAccessException)
        {
        }
    }
}
