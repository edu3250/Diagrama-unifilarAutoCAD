using System.Runtime.InteropServices;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using PvSld.AutoCAD.Render;
using PvSld.Bridge;
using CoreApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace PvSld.AutoCAD;

/// <summary>
/// Runs drawing work on the main thread: resolve the document, refuse if AutoCAD is busy, lock the
/// document, run the body in one transaction and commit only if the body returns. Any exception
/// disposes the uncommitted transaction, which rolls back every change.
/// </summary>
internal static partial class DocumentScope
{
    public static T Run<T>(string? documentName, bool write, Func<Transaction, Database, T> body)
    {
        var document = Resolve(documentName);
        ThrowIfBusy(document);

        DocumentLock documentLock;
        try
        {
            documentLock = document.LockDocument(
                write ? DocumentLockMode.Write : DocumentLockMode.Read, null, null, false);
        }
        catch (Autodesk.AutoCAD.Runtime.Exception ex)
        {
            throw new BusyException(
                BusyReasons.DocumentLocked,
                $"AutoCAD refused to lock '{document.Name}' ({ex.ErrorStatus}); a command is probably active. "
                + "Finish it or press Esc in AutoCAD, then retry.");
        }

        using (documentLock)
        {
            using var transaction = document.TransactionManager.StartTransaction();
            T result;
            try
            {
                result = body(transaction, document.Database);
            }
            catch (BridgeException)
            {
                throw;
            }
            catch (InjectedFailureException ex)
            {
                throw RolledBack(ex.Message, injected: true);
            }
            catch (Exception ex) when (ex is UnknownAttributeException or ArgumentException or KeyNotFoundException)
            {
                throw new BridgeException(BridgeErrorCodes.InvalidParams, ex.Message);
            }
#pragma warning disable CA1031 // Any AutoCAD failure is reported to the client after the rollback.
            catch (Exception ex)
#pragma warning restore CA1031
            {
                throw RolledBack($"{ex.GetType().Name}: {ex.Message}", injected: false);
            }

            if (write)
            {
                document.TransactionManager.QueueForGraphicsFlush();
            }

            transaction.Commit();
            return result;
        }
    }

    private static BridgeException RolledBack(string message, bool injected) =>
        new(
            BridgeErrorCodes.OperationFailed,
            $"{message}. The transaction was rolled back; the drawing is unchanged.",
            new System.Text.Json.Nodes.JsonObject { ["rolled_back"] = true, ["injected"] = injected });

    private static Document Resolve(string? name)
    {
        var manager = CoreApp.DocumentManager;
        if (name is null)
        {
            return manager.MdiActiveDocument
                ?? throw new BridgeException(
                    BridgeErrorCodes.DocumentNotFound, "No drawing is open in AutoCAD. Open or create a drawing and retry.");
        }

        var open = new List<string>();
        foreach (Document document in manager)
        {
            var fileName = Path.GetFileName(document.Name);
            open.Add(fileName);
            if (string.Equals(document.Name, name, StringComparison.OrdinalIgnoreCase)
                || string.Equals(fileName, name, StringComparison.OrdinalIgnoreCase))
            {
                return document;
            }
        }

        throw new BridgeException(
            BridgeErrorCodes.DocumentNotFound,
            $"No open drawing is named '{name}'. Open drawings: {string.Join(", ", open)}.");
    }

    /// <summary>Refuses work while AutoCAD shows a modal window or runs a command, script or LISP.</summary>
    private static void ThrowIfBusy(Document document)
    {
        var mainWindow = CoreApp.MainWindow?.Handle ?? IntPtr.Zero;
        if (mainWindow != IntPtr.Zero && !IsWindowEnabled(mainWindow))
        {
            throw new BusyException(
                BusyReasons.ModalDialog,
                "A modal dialog is open in AutoCAD. Close it, then retry.");
        }

        var command = document.CommandInProgress;
        if (!string.IsNullOrEmpty(command))
        {
            throw new BusyException(
                BusyReasons.CommandActive,
                $"AutoCAD is running the command '{command}'. Finish it or press Esc in AutoCAD, then retry.");
        }

        if (!CoreApp.IsQuiescent)
        {
            throw new BusyException(
                BusyReasons.NotQuiescent,
                "AutoCAD is running a command, script or LISP routine. Wait for it to finish (or press Esc), then retry.");
        }
    }

    [LibraryImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool IsWindowEnabled(IntPtr hWnd);
}
