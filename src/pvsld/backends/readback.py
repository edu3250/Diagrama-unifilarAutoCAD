"""Read a DXF back and verify it against the diagram that produced it (ADR-0001, point 5).

A successful write is not evidence. :func:`verify` reloads the file and checks, independently of the
code that drew it:

* ``audit()`` reports no errors and applies no fixes;
* the number of INSERTs per block equals the diagram's component count;
* every component round-trips by ``COMP_ID``: all its attribute values equal the diagram's
  (the S1 criterion "100 % attribute round-trip");
* every conductor LWPOLYLINE ends on the port it names, measured from the port data stored in the
  block XDATA transformed by the INSERT, within 0.01 mm, and every required port is the end of at
  least one conductor (no dangling ports);
* no drawing content, in a layout or in a block definition, lies on layer ``0``; the one exception
  is the overall paper-space viewport (id 1), which AutoCAD requires on layer ``0`` and which the
  verifier demands there (AUDIT: ``Paperspace vport layer Not "0"``);
* every used layer belongs to the house layer standard.

The same functions serve the MCP read-back tool of a later stage (``get_diagram_summary``).
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.document import Drawing
from ezdxf.lldxf.const import DXFValueError

from pvsld.backends.dxf import (
    BLOCK_FORMAT,
    INSTANCE_FORMAT,
    LAYOUT_NAME,
    WIRE_FORMAT,
)
from pvsld.core import layers
from pvsld.core.diagram import PORT_TOLERANCE_MM, Diagram, PortRef
from pvsld.symbols import APP_ID


@dataclass(frozen=True)
class PortData:
    """A port as stored in the block record XDATA (block-local coordinates)."""

    id: str
    kind: str
    direction: str
    x: float
    y: float
    required: bool


@dataclass(frozen=True)
class InsertData:
    block: str
    space: str
    x: float
    y: float
    layer: str
    attributes: dict[str, str]
    xdata_comp_id: str | None
    scale: float = 1.0

    @property
    def comp_id(self) -> str | None:
        return self.attributes.get("COMP_ID")


@dataclass(frozen=True)
class WireData:
    conn_id: str
    circuit_id: str
    kind: str
    start: str
    end: str
    points: tuple[tuple[float, float], ...]
    layer: str


@dataclass(frozen=True)
class Inventory:
    """Everything the verifier needs from a DXF document."""

    inserts: tuple[InsertData, ...]
    wires: tuple[WireData, ...]
    block_ports: dict[str, tuple[PortData, ...]]
    layer_counts: Counter[str]
    defined_layers: frozenset[str]
    layout_names: tuple[str, ...]
    overall_viewport_layers: dict[str, str]  # paper layout name -> layer of its viewport id 1

    @property
    def layer_zero_entities(self) -> int:
        """Drawing entities on layer 0; the overall viewport is counted apart."""
        return self.layer_counts.get(layers.OVERALL_VIEWPORT, 0)


def load_document(source: bytes | Path) -> Drawing:
    """Load a DXF from bytes or a path (UTF-8, as written by the backend)."""
    if isinstance(source, Path):
        return ezdxf.readfile(source)
    return ezdxf.read(io.StringIO(source.decode("utf-8")))


def _xdata(entity: Any) -> list[tuple[int, Any]]:
    try:
        return [(tag.code, tag.value) for tag in entity.get_xdata(APP_ID)]
    except DXFValueError:
        return []


def _parse_ports(tags: list[tuple[int, Any]]) -> tuple[PortData, ...]:
    if len(tags) < 3 or tags[0] != (1000, BLOCK_FORMAT):
        return ()
    count = tags[2][1]
    ports = []
    for index in range(count):
        chunk = tags[3 + index * 6 : 9 + index * 6]
        ports.append(
            PortData(
                id=chunk[0][1],
                kind=chunk[1][1],
                direction=chunk[2][1],
                x=chunk[3][1],
                y=chunk[4][1],
                required=bool(chunk[5][1]),
            )
        )
    return tuple(ports)


def read_inventory(doc: Drawing) -> Inventory:
    """Collect inserts, wires, port data and per-layer entity counts from ``doc``."""
    block_ports = {
        block.name: _parse_ports(_xdata(block.block_record))
        for block in doc.blocks
        if not block.name.startswith("*")
    }
    inserts: list[InsertData] = []
    wires: list[WireData] = []
    layer_counts: Counter[str] = Counter()
    overall_viewport_layers: dict[str, str] = {}
    spaces = [("model", doc.modelspace())]
    spaces += [("paper", layout) for layout in doc.layouts if layout.name != "Model"]

    def count(entity: Any) -> None:
        layer_counts[entity.dxf.layer] += 1

    for space, layout in spaces:
        for entity in layout:
            kind = entity.dxftype()
            if space == "paper" and kind == "VIEWPORT" and entity.dxf.get("id") == 1:
                overall_viewport_layers[layout.name] = entity.dxf.layer
                continue  # window frame of the sheet, not drawing content
            count(entity)
            if kind == "INSERT":
                for attrib in entity.attribs:
                    count(attrib)
                tags = _xdata(entity)
                inserts.append(
                    InsertData(
                        block=entity.dxf.name,
                        space=space,
                        x=entity.dxf.insert.x,
                        y=entity.dxf.insert.y,
                        layer=entity.dxf.layer,
                        attributes={a.dxf.tag: a.dxf.text for a in entity.attribs},
                        xdata_comp_id=tags[1][1] if tags[:1] == [(1000, INSTANCE_FORMAT)] else None,
                        scale=entity.dxf.get("xscale", 1.0),
                    )
                )
            elif kind == "LWPOLYLINE":
                tags = _xdata(entity)
                if tags[:1] == [(1000, WIRE_FORMAT)]:
                    wires.append(
                        WireData(
                            conn_id=tags[1][1],
                            circuit_id=tags[2][1],
                            kind=tags[3][1],
                            start=tags[4][1],
                            end=tags[5][1],
                            points=tuple((p[0], p[1]) for p in entity.get_points("xy")),
                            layer=entity.dxf.layer,
                        )
                    )
    for block in doc.blocks:
        if block.name.startswith("*"):
            continue
        for entity in block:
            count(entity)
    return Inventory(
        inserts=tuple(inserts),
        wires=tuple(wires),
        block_ports=block_ports,
        layer_counts=layer_counts,
        defined_layers=frozenset(layer.dxf.name for layer in doc.layers),
        layout_names=tuple(layout.name for layout in doc.layouts),
        overall_viewport_layers=overall_viewport_layers,
    )


@dataclass(frozen=True)
class ReadBackReport:
    """Measured result of verifying a DXF against its diagram."""

    audit_errors: int
    audit_fixes: int
    insert_counts: dict[str, int]
    expected_counts: dict[str, int]
    instances_checked: int
    instances_matched: int
    attributes_checked: int
    attributes_matched: int
    required_ports: int
    dangling_ports: tuple[str, ...]
    wire_ends_checked: int
    wire_ends_off_port: tuple[str, ...]
    layer_zero_entities: int
    problems: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> dict[str, Any]:
        """Plain JSON types, safe to return from a tool."""
        return {
            "ok": self.ok,
            "audit": {"errors": self.audit_errors, "fixes": self.audit_fixes},
            "inserts_per_block": self.insert_counts,
            "attribute_roundtrip": f"{self.attributes_matched}/{self.attributes_checked}",
            "dangling_ports": list(self.dangling_ports),
            "wire_ends_off_port": list(self.wire_ends_off_port),
            "entities_on_layer_0": self.layer_zero_entities,
            "problems": list(self.problems),
        }


def verify(diagram: Diagram, source: bytes | Path | Drawing) -> ReadBackReport:
    """Reload ``source`` (the bytes or path of the DXF) and check it against ``diagram``."""
    doc = load_document(source) if not isinstance(source, Drawing) else source
    auditor = doc.audit()
    inventory = read_inventory(doc)
    problems: list[str] = []

    if len(auditor.errors) or len(auditor.fixes):
        problems.append(f"audit: {len(auditor.errors)} errors, {len(auditor.fixes)} fixes")
    if LAYOUT_NAME not in inventory.layout_names:
        problems.append(f"layout {LAYOUT_NAME} is missing")
    else:
        sheet_viewport = inventory.overall_viewport_layers.get(LAYOUT_NAME)
        if sheet_viewport is None:
            problems.append(f"layout {LAYOUT_NAME} has no overall viewport (id 1)")
    for layout_name, layer in inventory.overall_viewport_layers.items():
        if layer != layers.OVERALL_VIEWPORT:
            problems.append(
                f"overall viewport of layout {layout_name} is on layer {layer}; "
                "AutoCAD requires layer 0"
            )

    counts = dict(Counter(i.block for i in inventory.inserts))
    expected = diagram.block_counts()
    if counts != expected:
        problems.append(f"INSERT counts {counts} differ from the model {expected}")

    by_id = {i.comp_id: i for i in inventory.inserts if i.comp_id is not None}
    matched_instances = matched_attributes = checked_attributes = 0
    for item in diagram.instances:
        found = by_id.get(item.comp_id)
        if found is None:
            problems.append(f"{item.comp_id}: no INSERT with this COMP_ID in the file")
            checked_attributes += len(item.attributes)
            continue
        expected_values = item.values
        hits = sum(
            1 for tag, value in expected_values.items() if found.attributes.get(tag) == value
        )
        checked_attributes += len(expected_values)
        matched_attributes += hits
        same = (
            hits == len(expected_values)
            and set(found.attributes) == set(expected_values)
            and found.block == item.symbol
            and found.xdata_comp_id == item.comp_id
            and found.layer == item.layer
        )
        if same:
            matched_instances += 1
        else:
            problems.append(
                f"{item.comp_id}: attributes, block, layer or XDATA differ from the model"
            )

    # Connectivity, measured from the file only.
    def world_port(ref: str) -> tuple[float, float] | None:
        port_ref = PortRef.parse(ref)
        insert = by_id.get(port_ref.comp_id)
        if insert is None:
            return None
        for port in inventory.block_ports.get(insert.block, ()):
            if port.id == port_ref.port:
                return (insert.x + port.x * insert.scale, insert.y + port.y * insert.scale)
        return None

    ends_checked = 0
    off_port: list[str] = []
    connected: set[str] = set()
    for wire in inventory.wires:
        for ref, point in ((wire.start, wire.points[0]), (wire.end, wire.points[-1])):
            ends_checked += 1
            expected_point = world_port(ref)
            if (
                expected_point is None
                or abs(expected_point[0] - point[0]) > PORT_TOLERANCE_MM
                or abs(expected_point[1] - point[1]) > PORT_TOLERANCE_MM
            ):
                off_port.append(f"{wire.conn_id}:{ref}")
            else:
                connected.add(ref)
    if len(inventory.wires) != len(diagram.connections):
        problems.append(
            f"{len(inventory.wires)} conductors in the file, "
            f"{len(diagram.connections)} in the model"
        )
    drawn = {w.conn_id: (w.start, w.end, w.points) for w in inventory.wires}
    for conn in diagram.connections:
        got = drawn.get(conn.id)
        want = (str(conn.start), str(conn.end), tuple((p.x, p.y) for p in conn.points))
        if got != want:
            problems.append(f"conductor {conn.id} differs from the model")

    required: list[str] = []
    for insert in inventory.inserts:
        for port in inventory.block_ports.get(insert.block, ()):
            if port.required and insert.comp_id is not None:
                required.append(f"{insert.comp_id}.{port.id}")
    dangling = tuple(ref for ref in required if ref not in connected)
    if off_port:
        problems.append(f"{len(off_port)} conductor ends are off their port: {off_port}")
    if dangling:
        problems.append(f"dangling ports: {list(dangling)}")
    if inventory.layer_zero_entities:
        problems.append(f"{inventory.layer_zero_entities} entities on layer 0")
    foreign = sorted(set(inventory.layer_counts) - layers.LAYER_NAMES)
    if foreign:
        problems.append(f"entities on layers outside the house standard: {foreign}")
    missing_layers = sorted(layers.LAYER_NAMES - inventory.defined_layers)
    if missing_layers:
        problems.append(f"house layers missing from the file: {missing_layers}")

    return ReadBackReport(
        audit_errors=len(auditor.errors),
        audit_fixes=len(auditor.fixes),
        insert_counts=counts,
        expected_counts=expected,
        instances_checked=len(diagram.instances),
        instances_matched=matched_instances,
        attributes_checked=checked_attributes,
        attributes_matched=matched_attributes,
        required_ports=len(required),
        dangling_ports=dangling,
        wire_ends_checked=ends_checked,
        wire_ends_off_port=tuple(off_port),
        layer_zero_entities=inventory.layer_zero_entities,
        problems=tuple(problems),
    )
