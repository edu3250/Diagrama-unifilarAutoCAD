using System.Text.Json;
using System.Text.Json.Nodes;

namespace PvSld.Bridge;

/// <summary>Typed accessors for request parameters that fail with actionable invalid-params errors.</summary>
public static class BridgeParams
{
    public static string RequireString(JsonObject? parameters, string name, int maxLength = 256)
    {
        return OptionalString(parameters, name, maxLength)
            ?? throw BridgeException.InvalidParams($"missing string parameter \"{name}\"");
    }

    public static string? OptionalString(JsonObject? parameters, string name, int maxLength = 256)
    {
        var node = parameters?[name];
        if (node is null)
        {
            return null;
        }

        if (node.GetValueKind() != JsonValueKind.String)
        {
            throw BridgeException.InvalidParams($"parameter \"{name}\" must be a string");
        }

        var value = node.GetValue<string>();
        if (value.Length > maxLength)
        {
            throw BridgeException.InvalidParams($"parameter \"{name}\" is longer than {maxLength} characters");
        }

        return value;
    }

    public static bool OptionalBool(JsonObject? parameters, string name, bool defaultValue = false)
    {
        var node = parameters?[name];
        return node?.GetValueKind() switch
        {
            null => defaultValue,
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => throw BridgeException.InvalidParams($"parameter \"{name}\" must be true or false"),
        };
    }

    public static int? OptionalInt(JsonObject? parameters, string name, int min = int.MinValue, int max = int.MaxValue)
    {
        var node = parameters?[name];
        if (node is null)
        {
            return null;
        }

        if (node.GetValueKind() != JsonValueKind.Number || !node.AsValue().TryGetValue(out int value))
        {
            throw BridgeException.InvalidParams($"parameter \"{name}\" must be an integer");
        }

        if (value < min || value > max)
        {
            throw BridgeException.InvalidParams($"parameter \"{name}\" must be between {min} and {max}");
        }

        return value;
    }

    /// <summary>Reads <c>[x, y]</c> or <c>[x, y, z]</c> (drawing units).</summary>
    public static (double X, double Y, double Z) RequirePoint(JsonNode? node, string name)
    {
        if (node is not JsonArray array || array.Count is < 2 or > 3)
        {
            throw BridgeException.InvalidParams($"\"{name}\" must be an array [x, y] or [x, y, z]");
        }

        var values = new double[3];
        for (var i = 0; i < array.Count; i++)
        {
            if (array[i]?.GetValueKind() != JsonValueKind.Number
                || !double.IsFinite(values[i] = array[i]!.GetValue<double>()))
            {
                throw BridgeException.InvalidParams($"\"{name}\" must contain finite numbers");
            }
        }

        return (values[0], values[1], values[2]);
    }

    /// <summary>Reads an object of string values (attribute tag to text).</summary>
    public static Dictionary<string, string> StringMap(JsonNode? node, string name, int maxValueLength = 256)
    {
        var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (node is null)
        {
            return map;
        }

        if (node is not JsonObject obj)
        {
            throw BridgeException.InvalidParams($"\"{name}\" must be an object of strings");
        }

        foreach (var (key, value) in obj)
        {
            if (value?.GetValueKind() != JsonValueKind.String)
            {
                throw BridgeException.InvalidParams($"\"{name}.{key}\" must be a string");
            }

            var text = value.GetValue<string>();
            if (text.Length > maxValueLength)
            {
                throw BridgeException.InvalidParams($"\"{name}.{key}\" is longer than {maxValueLength} characters");
            }

            map[key] = text;
        }

        return map;
    }

    public static JsonArray OptionalArray(JsonObject? parameters, string name, int maxItems)
    {
        var node = parameters?[name];
        if (node is null)
        {
            return [];
        }

        if (node is not JsonArray array)
        {
            throw BridgeException.InvalidParams($"parameter \"{name}\" must be an array");
        }

        if (array.Count > maxItems)
        {
            throw BridgeException.InvalidParams($"parameter \"{name}\" has more than {maxItems} items");
        }

        return array;
    }
}
