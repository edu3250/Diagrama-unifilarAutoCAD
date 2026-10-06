using System.Text.Json.Nodes;

namespace PvSld.Bridge;

/// <summary>An error that is reported to the client as a JSON-RPC error object.</summary>
public class BridgeException : Exception
{
    public BridgeException(int code, string message, JsonObject? data = null)
        : base(message)
    {
        Code = code;
        Data = data;
    }

    public int Code { get; }

    /// <summary>Optional structured details (<c>error.data</c>).</summary>
    public new JsonObject? Data { get; }

    public static BridgeException InvalidParams(string message) =>
        new(BridgeErrorCodes.InvalidParams, message);
}

/// <summary>AutoCAD cannot accept the request right now; the message tells the user what to do.</summary>
public sealed class BusyException : BridgeException
{
    public BusyException(string reason, string message, int retryAfterMs = 1000)
        : base(
            BridgeErrorCodes.Busy,
            message,
            new JsonObject { ["reason"] = reason, ["retry_after_ms"] = retryAfterMs })
    {
        Reason = reason;
    }

    public string Reason { get; }
}
