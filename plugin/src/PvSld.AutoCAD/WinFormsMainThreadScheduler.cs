using System.Windows.Forms;
using PvSld.Bridge;

namespace PvSld.AutoCAD;

/// <summary>
/// Marshals work onto AutoCAD's main thread through a hidden window created there: BeginInvoke
/// posts a window message that AutoCAD's message loop (or a modal loop) dispatches. The job then
/// runs in the application context, which is why every drawing job locks its document.
/// </summary>
internal sealed class WinFormsMainThreadScheduler : IMainThreadScheduler, IDisposable
{
    private readonly Control _control;

    /// <summary>Must be constructed on AutoCAD's main thread.</summary>
    public WinFormsMainThreadScheduler()
    {
        _control = new Control();
        _ = _control.Handle; // force the window handle onto the current (main) thread
    }

    public void Post(Action action)
    {
        ObjectDisposedException.ThrowIf(_control.IsDisposed, this);
        _control.BeginInvoke(action);
    }

    public void Dispose() => _control.Dispose();
}
