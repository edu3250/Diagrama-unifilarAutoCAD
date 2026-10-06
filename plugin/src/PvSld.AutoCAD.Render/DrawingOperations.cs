using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace PvSld.AutoCAD.Render;

/// <summary>
/// Database-only drawing operations. Every method works inside the caller's transaction and never
/// commits: the caller commits on success, and disposing an uncommitted transaction rolls back
/// everything these methods appended (including a block definition they created).
/// </summary>
public static class DrawingOperations
{
    public static InsertResult InsertBlock(Transaction tr, Database db, string blockName, AttributedInsert insert)
    {
        var blockId = TestSymbol.Ensure(tr, db, blockName, out var created);
        var block = AttributedBlock.Open(tr, blockId);
        block.Validate(insert.Attributes);
        var space = OpenModelSpace(tr, db, OpenMode.ForWrite);
        var reference = block.Insert(tr, db, space, insert.Position, insert.Attributes);
        return new InsertResult(reference.Handle.ToString(CultureInfo.InvariantCulture), ReadValues(tr, reference), created);
    }

    public static BatchResult RunBatch(Transaction tr, Database db, BatchSpec spec)
    {
        var blockId = TestSymbol.Ensure(tr, db, spec.BlockName, out var created);
        var block = AttributedBlock.Open(tr, blockId);
        foreach (var insert in spec.Inserts)
        {
            block.Validate(insert.Attributes); // reject bad input before anything is written
        }

        var space = OpenModelSpace(tr, db, OpenMode.ForWrite);
        var handles = new List<string>(spec.Inserts.Count);
        var appended = 0;
        foreach (var insert in spec.Inserts)
        {
            InjectFailureIfDue(spec, appended);
            handles.Add(block.Insert(tr, db, space, insert.Position, insert.Attributes).Handle.ToString(CultureInfo.InvariantCulture));
            appended++;
        }

        foreach (var segment in spec.Lines)
        {
            InjectFailureIfDue(spec, appended);
            var line = new Line(segment.Start, segment.End);
            line.SetDatabaseDefaults(db);
            space.AppendEntity(line);
            tr.AddNewlyCreatedDBObject(line, true);
            appended++;
        }

        InjectFailureIfDue(spec, appended); // "after everything, just before commit"
        return new BatchResult(spec.Inserts.Count, spec.Lines.Count, handles, created);
    }

    /// <summary>Reads one reference by handle, or every reference of a block name.</summary>
    public static IReadOnlyList<BlockAttributes> ReadAttributes(Transaction tr, Database db, string? handle, string? blockName)
    {
        if (handle is not null)
        {
            var id = ResolveHandle(db, handle);
            if (tr.GetObject(id, OpenMode.ForRead) is not BlockReference reference)
            {
                throw new ArgumentException($"handle {handle} is not a block reference");
            }

            return [Describe(tr, reference)];
        }

        var table = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
        if (blockName is null || !table.Has(blockName))
        {
            return [];
        }

        var definition = (BlockTableRecord)tr.GetObject(table[blockName], OpenMode.ForRead);
        var result = new List<BlockAttributes>();
        foreach (ObjectId id in definition.GetBlockReferenceIds(true, false))
        {
            if (!id.IsErased && tr.GetObject(id, OpenMode.ForRead) is BlockReference reference)
            {
                result.Add(Describe(tr, reference));
            }
        }

        result.Sort((a, b) => string.CompareOrdinal(a.Handle, b.Handle));
        return result;
    }

    public static DrawingSnapshot Snapshot(Transaction tr, Database db)
    {
        var space = OpenModelSpace(tr, db, OpenMode.ForRead);
        var handles = new List<string>();
        foreach (ObjectId id in space)
        {
            handles.Add(id.Handle.ToString(CultureInfo.InvariantCulture));
        }

        handles.Sort(StringComparer.Ordinal);
        var digest = Convert.ToHexStringLower(SHA256.HashData(Encoding.ASCII.GetBytes(string.Join(',', handles))));

        var table = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
        var names = new List<string>();
        foreach (ObjectId id in table)
        {
            var record = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
            if (!record.IsLayout && !record.IsAnonymous)
            {
                names.Add(record.Name);
            }
        }

        names.Sort(StringComparer.Ordinal);
        return new DrawingSnapshot(handles.Count, names, digest);
    }

    private static void InjectFailureIfDue(BatchSpec spec, int appended)
    {
        if (spec.InjectFailureAfter == appended)
        {
            throw new InjectedFailureException(appended);
        }
    }

    private static BlockTableRecord OpenModelSpace(Transaction tr, Database db, OpenMode mode) =>
        (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), mode);

    private static ObjectId ResolveHandle(Database db, string handle)
    {
        if (!long.TryParse(handle, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var value)
            || value <= 0)
        {
            throw new ArgumentException($"'{handle}' is not a hexadecimal entity handle");
        }

        try
        {
            var id = db.GetObjectId(false, new Handle(value), 0);
            if (id.IsNull || id.IsErased)
            {
                throw new KeyNotFoundException($"no entity with handle {handle} in this drawing");
            }

            return id;
        }
        catch (Autodesk.AutoCAD.Runtime.Exception)
        {
            throw new KeyNotFoundException($"no entity with handle {handle} in this drawing");
        }
    }

    private static BlockAttributes Describe(Transaction tr, BlockReference reference) =>
        new(reference.Handle.ToString(CultureInfo.InvariantCulture), reference.Name, reference.Position, ReadValues(tr, reference));

    private static Dictionary<string, string> ReadValues(Transaction tr, BlockReference reference)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (ObjectId id in reference.AttributeCollection)
        {
            var attribute = (AttributeReference)tr.GetObject(id, OpenMode.ForRead);
            values[attribute.Tag] = attribute.TextString;
        }

        return values;
    }
}

/// <summary>The simple test symbol used by the spike when a block does not exist yet.</summary>
public static class TestSymbol
{
    public static readonly IReadOnlyList<string> Tags = ["COMP_ID", "LABEL", "RATING"];

    public static ObjectId Ensure(Transaction tr, Database db, string name, out bool created)
    {
        var table = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
        if (table.Has(name))
        {
            created = false;
            return table[name];
        }

        table.UpgradeOpen();
        var record = new BlockTableRecord { Name = name, Origin = Point3d.Origin };
        var id = table.Add(record);
        tr.AddNewlyCreatedDBObject(record, true);

        var outline = new Polyline(4);
        outline.AddVertexAt(0, new Point2d(-10, -5), 0, 0, 0);
        outline.AddVertexAt(1, new Point2d(10, -5), 0, 0, 0);
        outline.AddVertexAt(2, new Point2d(10, 5), 0, 0, 0);
        outline.AddVertexAt(3, new Point2d(-10, 5), 0, 0, 0);
        outline.Closed = true;
        Append(tr, db, record, outline);
        Append(tr, db, record, new Circle(Point3d.Origin, Vector3d.ZAxis, 3));

        // COMP_ID is hidden (ADR-0001 point 6); LABEL and RATING are visible.
        AddAttribute(tr, db, record, "COMP_ID", "Component id", new Point3d(-10, -11, 0), 2.0, invisible: true);
        AddAttribute(tr, db, record, "LABEL", "Label", new Point3d(-10, 7, 0), 2.5, invisible: false);
        AddAttribute(tr, db, record, "RATING", "Rating", new Point3d(-10, -8, 0), 2.0, invisible: false);
        created = true;
        return id;
    }

    private static void Append(Transaction tr, Database db, BlockTableRecord record, Entity entity)
    {
        entity.SetDatabaseDefaults(db);
        record.AppendEntity(entity);
        tr.AddNewlyCreatedDBObject(entity, true);
    }

    private static void AddAttribute(
        Transaction tr, Database db, BlockTableRecord record, string tag, string prompt, Point3d position, double height, bool invisible)
    {
        var definition = new AttributeDefinition
        {
            Tag = tag,
            Prompt = prompt,
            TextString = string.Empty,
        };
        definition.SetDatabaseDefaults(db);
        definition.Position = position;
        definition.Height = height;
        definition.Invisible = invisible;
        record.AppendEntity(definition);
        tr.AddNewlyCreatedDBObject(definition, true);
    }
}

/// <summary>A block definition's non-constant attribute definitions, opened once per transaction.</summary>
public sealed class AttributedBlock
{
    private readonly ObjectId _blockId;
    private readonly IReadOnlyList<AttributeDefinition> _definitions;

    private AttributedBlock(ObjectId blockId, string name, IReadOnlyList<AttributeDefinition> definitions)
    {
        _blockId = blockId;
        Name = name;
        _definitions = definitions;
        Tags = [.. definitions.Select(d => d.Tag)];
    }

    public string Name { get; }

    public IReadOnlyList<string> Tags { get; }

    public static AttributedBlock Open(Transaction tr, ObjectId blockId)
    {
        var record = (BlockTableRecord)tr.GetObject(blockId, OpenMode.ForRead);
        var definitions = new List<AttributeDefinition>();
        if (record.HasAttributeDefinitions)
        {
            foreach (ObjectId id in record)
            {
                if (tr.GetObject(id, OpenMode.ForRead) is AttributeDefinition definition && !definition.Constant)
                {
                    definitions.Add(definition);
                }
            }
        }

        return new AttributedBlock(blockId, record.Name, definitions);
    }

    public void Validate(IReadOnlyDictionary<string, string> values)
    {
        var unknown = values.Keys
            .Where(key => !Tags.Contains(key, StringComparer.OrdinalIgnoreCase))
            .ToList();
        if (unknown.Count > 0)
        {
            throw new UnknownAttributeException(Name, unknown, Tags);
        }
    }

    public BlockReference Insert(Transaction tr, Database db, BlockTableRecord space, Point3d position, IReadOnlyDictionary<string, string> values)
    {
        var reference = new BlockReference(position, _blockId);
        reference.SetDatabaseDefaults(db);
        space.AppendEntity(reference);
        tr.AddNewlyCreatedDBObject(reference, true);

        foreach (var definition in _definitions)
        {
            var attribute = new AttributeReference();
            attribute.SetDatabaseDefaults(db);
            attribute.SetAttributeFromBlock(definition, reference.BlockTransform);
            attribute.TextString = Lookup(values, definition.Tag) ?? definition.TextString;
            reference.AttributeCollection.AppendAttribute(attribute);
            tr.AddNewlyCreatedDBObject(attribute, true);
        }

        return reference;
    }

    private static string? Lookup(IReadOnlyDictionary<string, string> values, string tag)
    {
        if (values.TryGetValue(tag, out var value))
        {
            return value;
        }

        foreach (var (key, candidate) in values)
        {
            if (string.Equals(key, tag, StringComparison.OrdinalIgnoreCase))
            {
                return candidate;
            }
        }

        return null;
    }
}
