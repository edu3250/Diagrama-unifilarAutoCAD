"""Bill of materials of an installation: what to buy, read from the specification.

Quantities come from the spec: modules from the strings, protections from ``dc_bos`` and
``ac_bos``, conductor and conduit lengths from the circuits (one way, no waste allowance). A
device the catalogue chose carries its reference (``model``); otherwise its ratings describe it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pvsld.core.calc import Derived
from pvsld.core.model import Circuit, PvSystemSpec

STRING_FUSE, STRING_BREAKER, BOX_SWITCH = "FUS-", "DCB-", "DCD-CD"


@dataclass(frozen=True)
class BomLine:
    """One line of the bill of materials."""

    group: str
    item: str
    description: str
    quantity: float
    unit: str


def _g(value: float) -> str:
    return f"{value:g}"


BRANDS = {
    "SQUARED": "Square D",
    "LITTELFUSE": "Littelfuse",
    "EATON": "Eaton",
    "SUNTREE": "Suntree",
    "VIAKON": "Viakon",
    "SCHNEIDER": "Schneider",
}


def device_name(model: str | None, fallback: str = "") -> str:
    """A catalogue reference as people read it: ``SQUARED-QO215`` -> ``Square D QO215``."""
    if not model:
        return fallback
    brand, _, rest = model.partition("-")
    if not rest:
        return model
    return f"{BRANDS.get(brand, brand.title())} {rest}"


def _raceway_of(spec: PvSystemSpec, circuit: Circuit) -> Circuit:
    if circuit.raceway.ref is None:
        return circuit
    return next(c for c in spec.circuits if c.id == circuit.raceway.ref)


def bill_of_materials(spec: PvSystemSpec, derived: Derived) -> list[BomLine]:
    """Every part of the installation, grouped as the owner reads a quote."""
    lines: list[BomLine] = []
    add = lines.append
    by_module = {m.id: m for m in spec.modules}
    for module_id in dict.fromkeys(s.module for s in spec.strings):
        m = by_module[module_id]
        count = sum(s.n_series for s in spec.strings if s.module == module_id)
        add(
            BomLine(
                "Generación",
                "Módulo fotovoltaico",
                f"{m.manufacturer} {m.model}, {_g(m.pmax_w)} W",
                count,
                "pza",
            )
        )
    for inv in spec.inverters:
        add(
            BomLine(
                "Generación",
                "Inversor",
                f"{inv.manufacturer} {inv.model}, {_g(inv.pac_w / 1000)} kW, {_g(inv.vac_v)} V",
                inv.qty,
                "pza",
            )
        )

    dc = spec.dc_bos
    fuses = [d for d in dc.disconnects if d.id.startswith(STRING_FUSE)]
    breakers = [d for d in dc.disconnects if d.id.startswith(STRING_BREAKER)]
    switches = [d for d in dc.disconnects if d.id.startswith(BOX_SWITCH)]
    box = "Caja de protecciones CD"
    if fuses:
        f = fuses[0]
        add(
            BomLine(
                box,
                "Fusible gPV 10×38 mm",
                f"{device_name(f.model) or 'gPV'} {_g(f.ie_a)} A, {_g(f.ue_v)} V cd",
                f.poles * len(fuses),
                "pza",
            )
        )
        add(
            BomLine(
                box,
                "Portafusible-seccionador",
                f"{f.poles} polos, 10×38 mm, {_g(f.ue_v)} V cd",
                len(fuses),
                "pza",
            )
        )
    if breakers:
        b = breakers[0]
        add(
            BomLine(
                box,
                "Interruptor termomagnético de CD",
                f"{device_name(b.model) or 'ITM CD'} {b.poles}P {_g(b.ie_a)} A, {_g(b.ue_v)} V cd",
                len(breakers),
                "pza",
            )
        )
    for s in switches:
        add(
            BomLine(
                box,
                "Seccionador FV",
                f"{device_name(s.model) or 'Seccionador'} "
                f"{s.poles} polos, {_g(s.ie_a)} A, {_g(s.ue_v)} V cd",
                1,
                "pza",
            )
        )
    for spd in dc.spds:
        volts = spd.ucpv_v if spd.ucpv_v is not None else spd.uc_v
        add(
            BomLine(
                box if fuses or breakers else "Protecciones CD",
                "DPS de CD",
                f"Tipo {spd.spd_type}"
                + (f", Ucpv {_g(volts)} V" if volts else "")
                + f", In {_g(spd.in_ka)} kA",
                1,
                "pza",
            )
        )
    if fuses or breakers:
        n = len(spec.strings)
        add(BomLine(box, "Conector tipo MC4", "Par macho/hembra", n, "par"))
        add(BomLine(box, "Gabinete", "Caja de protecciones CD con terminales", 1, "pza"))

    for circuit in spec.circuits:
        wires = circuit.conductors
        count = wires.qty + (1 if circuit.neutral is not None else 0)
        what = f"{wires.size} {wires.material} {wires.insulation}"
        add(BomLine("Conductores", f"Circuito {circuit.id}", what, count * circuit.length_m, "m"))
        add(
            BomLine(
                "Conductores",
                f"Tierra de {circuit.id}",
                f"{circuit.egc.size} {circuit.egc.type}",
                circuit.length_m,
                "m",
            )
        )
    for circuit in spec.circuits:
        if circuit.raceway.ref is not None or circuit.raceway.type is None:
            continue
        r = circuit.raceway
        size = f" {_g(r.trade_size_mm)} mm" if r.trade_size_mm else ""
        add(
            BomLine(
                "Canalización",
                f"Tubo {r.type}",
                f"{r.type}{size} para {circuit.id}",
                circuit.length_m,
                "m",
            )
        )

    ac = spec.ac_bos
    for o in ac.ocpds:
        add(
            BomLine(
                "Lado CA",
                f"Interruptor termomagnético {o.id}",
                f"{device_name(o.model) or 'ITM'} {o.poles}P {_g(o.rating_a)} A, {_g(o.kaic_ka)} kA",
                1,
                "pza",
            )
        )
    for main in ac.main_breakers:
        kaic = f", {_g(main.kaic_ka)} kA" if main.kaic_ka else ""
        add(
            BomLine(
                "Lado CA",
                f"Interruptor principal {main.id}",
                f"{device_name(main.model) or 'ITM'} {main.poles}P {_g(main.rating_a)} A{kaic} "
                "(existente)",
                1,
                "pza",
            )
        )
    for spd in ac.spds:
        add(
            BomLine(
                "Lado CA",
                "DPS de CA",
                f"Tipo {spd.spd_type}"
                + (f", Uc {_g(spd.uc_v)} V" if spd.uc_v else "")
                + f", In {_g(spd.in_ka)} kA",
                1,
                "pza",
            )
        )

    g = spec.grounding
    for e in g.electrodes:
        add(
            BomLine(
                "Puesta a tierra",
                "Electrodo",
                f"{e.type.capitalize()} {_g(e.length_m)} m",
                e.qty,
                "pza",
            )
        )
    add(
        BomLine(
            "Puesta a tierra",
            "Conductor del electrodo (GEC)",
            f"CD {g.gec_dc} / CA {g.gec_ac} Cu desnudo",
            1,
            "lote",
        )
    )
    for meter in ac.meters:
        add(
            BomLine(
                "Medición",
                "Medidor bidireccional" if meter.bidirectional else "Medidor",
                f"Lo instala {meter.owner}",
                1,
                "pza",
            )
        )
    return lines


def bom_text(spec: PvSystemSpec, derived: Derived, lines: list[BomLine] | None = None) -> str:
    """The plain-text summary shown to the user after a design (monospace-friendly)."""
    lines = lines if lines is not None else bill_of_materials(spec, derived)
    width = max(len(line.item) for line in lines) + 2
    out = [
        f"RESUMEN DE LA INSTALACIÓN — {derived.kwp_total:.2f} kWp / "
        f"{derived.kwac_total:.2f} kW CA (CD/CA {derived.dc_ac_ratio:.2f})"
    ]
    group = None
    for line in lines:
        if line.group != group:
            group = line.group
            out.append(f"{group}:")
        quantity = f"{line.quantity:g} {line.unit}"
        out.append(f"  {line.item.ljust(width, '.')} {quantity:>8}  {line.description}")
    out.append("Longitudes de un sentido, sin desperdicio: agregue la holgura de obra.")
    return "\n".join(out)
