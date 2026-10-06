using System.Text.Json;
using System.Text.Json.Nodes;

namespace PvSld.Bridge;

/// <summary>A parsed JSON-RPC 2.0 request. Notifications (no id) and batches are not supported.</summary>
public sealed record JsonRpcRequest(JsonNode Id, string Method, JsonObject? Params);

/// <summary>Parses requests and formats responses, one JSON object per line.</summary>
public static class JsonRpc
{
    public static JsonRpcRequest Parse(ReadOnlySpan<byte> line)
    {
        JsonNode? node;
        try
        {
            node = JsonNode.Parse(line);
        }
        catch (JsonException ex)
        {
            throw new BridgeException(BridgeErrorCodes.ParseError, $"invalid JSON: {ex.Message}");
        }

        if (node is not JsonObject message)
        {
            throw new BridgeException(
                BridgeErrorCodes.InvalidRequest, "a request must be one JSON object per line");
        }

        if (message["jsonrpc"]?.GetValueKind() != JsonValueKind.String
            || message["jsonrpc"]!.GetValue<string>() != "2.0")
        {
            throw new BridgeException(BridgeErrorCodes.InvalidRequest, "\"jsonrpc\" must be \"2.0\"");
        }

        var id = message["id"];
        if (id is null || id.GetValueKind() is not (JsonValueKind.String or JsonValueKind.Number))
        {
            throw new BridgeException(
                BridgeErrorCodes.InvalidRequest, "\"id\" must be a string or a number (notifications are not supported)");
        }

        if (message["method"]?.GetValueKind() != JsonValueKind.String)
        {
            throw new BridgeException(BridgeErrorCodes.InvalidRequest, "\"method\" must be a string");
        }

        var parameters = message["params"];
        if (parameters is not null and not JsonObject)
        {
            throw new BridgeException(
                BridgeErrorCodes.InvalidRequest, "\"params\" must be an object (by-name parameters only)");
        }

        return new JsonRpcRequest(id.DeepClone(), message["method"]!.GetValue<string>(), (JsonObject?)parameters?.DeepClone());
    }

    /// <summary>Best effort: recover the id of a request that failed validation.</summary>
    public static JsonNode? TryGetId(ReadOnlySpan<byte> line)
    {
        try
        {
            var id = JsonNode.Parse(line) is JsonObject o ? o["id"] : null;
            return id?.GetValueKind() is JsonValueKind.String or JsonValueKind.Number ? id.DeepClone() : null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    public static string Result(JsonNode? id, JsonNode? result) =>
        new JsonObject
        {
            ["jsonrpc"] = "2.0",
            ["id"] = id?.DeepClone(),
            ["result"] = result?.DeepClone(),
        }.ToJsonString();

    public static string Error(JsonNode? id, int code, string message, JsonObject? data = null)
    {
        var error = new JsonObject { ["code"] = code, ["message"] = message };
        if (data is not null)
        {
            error["data"] = data.DeepClone();
        }

        return new JsonObject { ["jsonrpc"] = "2.0", ["id"] = id?.DeepClone(), ["error"] = error }.ToJsonString();
    }
}
