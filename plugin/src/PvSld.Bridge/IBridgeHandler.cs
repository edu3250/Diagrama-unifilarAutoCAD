using System.Text.Json.Nodes;

namespace PvSld.Bridge;

/// <summary>Executes an authenticated request. Throw <see cref="BridgeException"/> for reportable errors.</summary>
public interface IBridgeHandler
{
    Task<JsonNode?> HandleAsync(string method, JsonObject? parameters, CancellationToken cancellationToken);
}
