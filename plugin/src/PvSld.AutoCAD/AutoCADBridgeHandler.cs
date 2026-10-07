using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.Geometry;
using PvSld.AutoCAD.Render;
using PvSld.Bridge;
using CoreApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace PvSld.AutoCAD;

/// <summary>
/// The allowlisted operations. Parameters are validated on the pipe thread; only the drawing work
/// itself is marshalled to AutoCAD's main thread.
/// </summary>
internal sealed partial class AutoCADBridgeHandler(MainThreadJobRunner runner, HostInfo host) : IBridgeHandler
{
    private const int MaxBatchItems = 5000;

    public Task<JsonNode?> HandleAsync(string method, JsonObject? parameters, CancellationToken cancellationToken) =>
        method switch
        {
            BridgeProtocol.Methods.Ping => PingAsync(parameters, cancellationToken),
            BridgeProtocol.Methods.InsertBlock => InsertBlockAsync(parameters, cancellationToken),
            BridgeProtocol.Methods.ReadAttributes => ReadAttributesAsync(parameters, cancellationToken),
            BridgeProtocol.Methods.Batch => BatchAsync(parameters, cancellationToken),
            BridgeProtocol.Methods.DrawingStats => DrawingStatsAsync(parameters, cancellationToken),
            _ => throw new BridgeException(
                BridgeErrorCodes.MethodNotFound,
                $"unknown method '{method}'; the bridge accepts only: {string.Join(", ", BridgeProtocol.Methods.All)}"),
        };

    private async Task<JsonNode?> PingAsync(JsonObject? parameters, CancellationToken cancellationToken)
    {
        var viaMainThread = BridgeParams.OptionalBool(parameters, "main_thread");
        var result = new JsonObject
        {
            ["pong"] = true,
            ["pid"] = host.Pid,
            ["host_version"] = host.HostVersion,
            ["server_version"] = host.ServerVersion,
            ["main_thread"] = viaMainThread,
        };
        if (viaMainThread)
        {
            result["documents"] = await runner.RunAsync(() => CoreApp.DocumentManager.Count, cancellationToken)
                .ConfigureAwait(false);
        }

        return result;
    }

    private async Task<JsonNode?> InsertBlockAsync(JsonObject? parameters, CancellationToken cancellationToken)
    {
        var document = BridgeParams.OptionalString(parameters, "document");
        var block = BlockName(parameters);
        var insert = new AttributedInsert(
            ToPoint(BridgeParams.RequirePoint(parameters?["position"], "position")),
            BridgeParams.StringMap(parameters?["attributes"], "attributes"));

        var result = await runner.RunAsync(
            () => DocumentScope.Run(document, write: true, (tr, db) => DrawingOperations.InsertBlock(tr, db, block, insert)),
            cancellationToken).ConfigureAwait(false);

        return new JsonObject
        {
            ["handle"] = result.Handle,
            ["attributes"] = ToJson(result.Attributes),
            ["created_block_definition"] = result.CreatedBlockDefinition,
        };
    }

    private async Task<JsonNode?> ReadAttributesAsync(JsonObject? parameters, CancellationToken cancellationToken)
    {
        var document = BridgeParams.OptionalString(parameters, "document");
        var handle = BridgeParams.OptionalString(parameters, "handle", maxLength: 16);
        var block = parameters?["block"] is null ? null : BlockName(parameters);
        if ((handle is null) == (block is null))
        {
            throw BridgeException.InvalidParams("give exactly one of \"handle\" or \"block\"");
        }

        var references = await runner.RunAsync(
            () => DocumentScope.Run(document, write: false, (tr, db) => DrawingOperations.ReadAttributes(tr, db, handle, block)),
            cancellationToken).ConfigureAwait(false);

        var items = new JsonArray();
        foreach (var reference in references)
        {
            items.Add(new JsonObject
            {
                ["handle"] = reference.Handle,
                ["block"] = reference.BlockName,
                ["position"] = new JsonArray(reference.Position.X, reference.Position.Y, reference.Position.Z),
                ["attributes"] = ToJson(reference.Attributes),
            });
        }

        return new JsonObject { ["references"] = items };
    }

    private async Task<JsonNode?> BatchAsync(JsonObject? parameters, CancellationToken cancellationToken)
    {
        var document = BridgeParams.OptionalString(parameters, "document");
        var block = BlockName(parameters);
        var inserts = new List<AttributedInsert>();
        foreach (var item in BridgeParams.OptionalArray(parameters, "inserts", MaxBatchItems))
        {
            var insert = item as JsonObject ?? throw BridgeException.InvalidParams("each insert must be an object");
            inserts.Add(new AttributedInsert(
                ToPoint(BridgeParams.RequirePoint(insert["position"], "inserts[].position")),
                BridgeParams.StringMap(insert["attributes"], "inserts[].attributes")));
        }

        var lines = new List<LineSegment>();
        foreach (var item in BridgeParams.OptionalArray(parameters, "lines", MaxBatchItems))
        {
            var line = item as JsonObject ?? throw BridgeException.InvalidParams("each line must be an object");
            lines.Add(new LineSegment(
                ToPoint(BridgeParams.RequirePoint(line["start"], "lines[].start")),
                ToPoint(BridgeParams.RequirePoint(line["end"], "lines[].end"))));
        }

        if (inserts.Count + lines.Count > MaxBatchItems)
        {
            throw BridgeException.InvalidParams($"a batch may hold at most {MaxBatchItems} inserts and lines in total");
        }

        var spec = new BatchSpec(
            block,
            inserts,
            lines,
            BridgeParams.OptionalInt(parameters, "inject_failure_after", min: 0, max: MaxBatchItems));
        var clock = System.Diagnostics.Stopwatch.StartNew();
        var result = await runner.RunAsync(
            () =>
            {
                var started = System.Diagnostics.Stopwatch.StartNew();
                var batch = DocumentScope.Run(document, write: true, (tr, db) => DrawingOperations.RunBatch(tr, db, spec));
                return (batch, started.Elapsed.TotalMilliseconds);
            },
            cancellationToken).ConfigureAwait(false);

        return new JsonObject
        {
            ["inserted"] = result.batch.Inserted,
            ["lines"] = result.batch.Lines,
            ["handles"] = new JsonArray([.. result.batch.Handles.Select(h => (JsonNode)h)]),
            ["created_block_definition"] = result.batch.CreatedBlockDefinition,
            ["main_thread_ms"] = Math.Round(result.TotalMilliseconds, 3),
            ["server_ms"] = Math.Round(clock.Elapsed.TotalMilliseconds, 3),
        };
    }

    private async Task<JsonNode?> DrawingStatsAsync(JsonObject? parameters, CancellationToken cancellationToken)
    {
        var document = BridgeParams.OptionalString(parameters, "document");
        var snapshot = await runner.RunAsync(
            () => DocumentScope.Run(document, write: false, DrawingOperations.Snapshot),
            cancellationToken).ConfigureAwait(false);
        return new JsonObject
        {
            ["modelspace_entities"] = snapshot.ModelSpaceEntities,
            ["block_definitions"] = new JsonArray([.. snapshot.BlockDefinitions.Select(n => (JsonNode)n)]),
            ["modelspace_digest"] = snapshot.ModelSpaceDigest,
        };
    }

    private static string BlockName(JsonObject? parameters)
    {
        var name = BridgeParams.RequireString(parameters, "block", maxLength: 64);
        if (!BlockNamePattern().IsMatch(name))
        {
            throw BridgeException.InvalidParams("\"block\" may contain only letters, digits, '_' and '-' (1-64 characters)");
        }

        return name;
    }

    private static Point3d ToPoint((double X, double Y, double Z) p) => new(p.X, p.Y, p.Z);

    private static JsonObject ToJson(IReadOnlyDictionary<string, string> values)
    {
        var json = new JsonObject();
        foreach (var (tag, text) in values)
        {
            json[tag] = text;
        }

        return json;
    }

    [GeneratedRegex("^[A-Za-z0-9_-]{1,64}$")]
    private static partial Regex BlockNamePattern();
}
