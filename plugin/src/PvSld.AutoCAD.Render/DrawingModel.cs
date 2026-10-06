using Autodesk.AutoCAD.Geometry;

namespace PvSld.AutoCAD.Render;

/// <summary>One attributed block reference to create.</summary>
public sealed record AttributedInsert(Point3d Position, IReadOnlyDictionary<string, string> Attributes);

/// <summary>One line segment to create in model space.</summary>
public sealed record LineSegment(Point3d Start, Point3d End);

/// <summary>
/// A batch materialized in one transaction. <see cref="InjectFailureAfter"/> is a test hook: after
/// that many entities have been appended the batch throws, so the caller can prove that the
/// transaction rolls back and the drawing is left unchanged.
/// </summary>
public sealed record BatchSpec(
    string BlockName,
    IReadOnlyList<AttributedInsert> Inserts,
    IReadOnlyList<LineSegment> Lines,
    int? InjectFailureAfter = null);

public sealed record BatchResult(int Inserted, int Lines, IReadOnlyList<string> Handles, bool CreatedBlockDefinition);

public sealed record InsertResult(string Handle, IReadOnlyDictionary<string, string> Attributes, bool CreatedBlockDefinition);

public sealed record BlockAttributes(string Handle, string BlockName, Point3d Position, IReadOnlyDictionary<string, string> Attributes);

/// <summary>A cheap fingerprint used to prove that a failed operation left the drawing unchanged.</summary>
public sealed record DrawingSnapshot(int ModelSpaceEntities, IReadOnlyList<string> BlockDefinitions, string ModelSpaceDigest);

/// <summary>Thrown by the <see cref="BatchSpec.InjectFailureAfter"/> test hook.</summary>
public sealed class InjectedFailureException(int afterEntities)
    : Exception($"injected failure after {afterEntities} entities (test hook)")
{
    public int AfterEntities { get; } = afterEntities;
}

/// <summary>A request names an attribute tag the block does not define.</summary>
public sealed class UnknownAttributeException(string blockName, IEnumerable<string> unknown, IEnumerable<string> known)
    : Exception(
        $"block '{blockName}' has no attribute(s) {string.Join(", ", unknown)}; "
        + $"its tags are {string.Join(", ", known)}")
{
}
