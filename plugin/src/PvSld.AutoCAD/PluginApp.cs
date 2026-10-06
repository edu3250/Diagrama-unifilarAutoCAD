using System.Reflection;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.Runtime;
using CoreApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

[assembly: ExtensionApplication(typeof(PvSld.AutoCAD.PluginApp))]
[assembly: CommandClass(typeof(PvSld.AutoCAD.Commands))]

namespace PvSld.AutoCAD;

/// <summary>
/// Entry point that AutoCAD calls on NETLOAD (Initialize) and on shutdown (Terminate). Starting the
/// bridge is all it does; neither method may throw, because AutoCAD would show the failure as a
/// modal dialog.
/// </summary>
public sealed class PluginApp : IExtensionApplication
{
    private static BridgeHost? s_host;

    internal static BridgeHost? Host => s_host;

    public void Initialize()
    {
        AppDomain.CurrentDomain.AssemblyResolve += ResolveSibling;
        try
        {
            StartBridge();
        }
#pragma warning disable CA1031 // Report, never throw, from Initialize.
        catch (System.Exception ex)
#pragma warning restore CA1031
        {
            WriteMessage($"\npvsld bridge failed to start: {ex.GetType().Name}: {ex.Message}\n");
        }
    }

    public void Terminate()
    {
        try
        {
            s_host?.Dispose();
        }
#pragma warning disable CA1031 // AutoCAD is shutting down; nothing useful can be done with the error.
        catch (System.Exception)
#pragma warning restore CA1031
        {
        }

        s_host = null;
    }

    internal static void WriteMessage(string message) =>
        CoreApp.DocumentManager.MdiActiveDocument?.Editor.WriteMessage(message);

    // Kept out of Initialize so the sibling-assembly resolver is registered before the JIT needs
    // PvSld.Bridge / PvSld.AutoCAD.Render.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void StartBridge()
    {
        s_host = BridgeHost.Start();
        WriteMessage($"\npvsld bridge {BridgeHost.ServerVersion} listening on \\\\.\\pipe\\{s_host.PipeName}\n");
    }

    private static Assembly? ResolveSibling(object? sender, ResolveEventArgs args)
    {
        var name = new AssemblyName(args.Name).Name;
        if (name is not ("PvSld.Bridge" or "PvSld.AutoCAD.Render"))
        {
            return null;
        }

        var directory = Path.GetDirectoryName(typeof(PluginApp).Assembly.Location);
        var path = directory is null ? null : Path.Combine(directory, name + ".dll");
        return path is not null && File.Exists(path) ? Assembly.LoadFrom(path) : null;
    }
}
