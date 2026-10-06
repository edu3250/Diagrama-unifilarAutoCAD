using Autodesk.AutoCAD.Runtime;

namespace PvSld.AutoCAD;

/// <summary>Command-line diagnostics for the bridge.</summary>
public sealed class Commands
{
    /// <summary>PVSLDBRIDGE: print the pipe name, connection and request counters.</summary>
    [CommandMethod("PVSLDBRIDGE", CommandFlags.Modal)]
    public static void Status() =>
        PluginApp.WriteMessage("\n" + (PluginApp.Host?.Status() ?? "pvsld bridge is not running") + "\n");
}
