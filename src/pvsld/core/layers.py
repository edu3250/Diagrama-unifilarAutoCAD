"""House layer standard of the sheet (vault note "SLD Drafting Conventions").

Format ``D-MMMM-mmmm``: discipline ``E`` (electrical) or ``G`` (general), major group, minor
group. Regulation prescribes no layer standard (ADR-0001), so this is a project convention that
doubles as a semantic tag for automated checks (all DC conductors live on ``E-PVDC-COND``).
Layer ``0`` is never used for drawing content: ``tests`` assert that no entity lands on it. The one
exception is the overall paper-space viewport (viewport id 1) of each layout, which AutoCAD requires
on layer ``0`` (AUDIT: ``Paperspace vport layer Not "0"``, spike S4); see :data:`OVERALL_VIEWPORT`.

Colours are AutoCAD Color Index values; line weights are in hundredths of a millimetre.
"""

from __future__ import annotations

from dataclasses import dataclass

DC_EQUIPMENT = "E-PVDC-EQPM"
DC_CONDUCTORS = "E-PVDC-COND"
AC_EQUIPMENT = "E-PVAC-EQPM"
AC_CONDUCTORS = "E-PVAC-COND"
UTILITY_EQUIPMENT = "E-UTIL-EQPM"
BATTERY_EQUIPMENT = "E-BATT-EQPM"
GROUNDING = "E-GRND-COND"
COMMUNICATIONS = "E-COMM-COND"
ENCLOSURES = "E-ANNO-ENCL"
TAGS = "E-ANNO-TAGS"
TABLES = "E-ANNO-TABL"
NOTES = "E-ANNO-NOTE"
LABELS = "E-ANNO-LABL"
TITLE_BLOCK = "G-ANNO-TTLB"
REVISIONS = "G-ANNO-REVS"
NON_PLOT = "G-ANNO-NPLT"

# The overall paper-space viewport (id 1) is the only entity that lives on layer 0.
OVERALL_VIEWPORT = "0"


@dataclass(frozen=True)
class LayerDef:
    """One layer of the house standard."""

    name: str
    aci: int
    lineweight: int
    linetype: str
    description_es: str
    plot: bool = True


LAYERS: tuple[LayerDef, ...] = (
    LayerDef(DC_EQUIPMENT, 5, 35, "CONTINUOUS", "Ramas FV, desconectadores y DPS de CD"),
    LayerDef(DC_CONDUCTORS, 5, 50, "CONTINUOUS", "Conductores de CD"),
    LayerDef(AC_EQUIPMENT, 1, 35, "CONTINUOUS", "Inversor, interruptores, tableros y DPS de CA"),
    LayerDef(AC_CONDUCTORS, 1, 50, "CONTINUOUS", "Conductores y barras de CA"),
    LayerDef(UTILITY_EQUIPMENT, 6, 35, "CONTINUOUS", "Red, medidores, TC/TP y equipo de MT"),
    LayerDef(BATTERY_EQUIPMENT, 30, 35, "CONTINUOUS", "Baterías y equipo de transferencia"),
    LayerDef(GROUNDING, 3, 35, "DASHED", "Tierras, puentes y electrodos"),
    LayerDef(COMMUNICATIONS, 8, 25, "DASHED", "Monitoreo y comunicaciones"),
    LayerDef(ENCLOSURES, 8, 25, "DASHDOT", "Envolventes y zonas CD/CA"),
    LayerDef(TAGS, 7, 25, "CONTINUOUS", "Etiquetas de equipo y datos de conductores"),
    LayerDef(TABLES, 7, 18, "CONTINUOUS", "Tablas de ramas, conductores y protecciones"),
    LayerDef(NOTES, 7, 18, "CONTINUOUS", "Notas generales y simbología"),
    LayerDef(LABELS, 7, 25, "CONTINUOUS", "Rótulos y advertencias requeridos"),
    LayerDef(TITLE_BLOCK, 7, 70, "CONTINUOUS", "Marco y cuadro de datos del plano"),
    LayerDef(REVISIONS, 7, 25, "CONTINUOUS", "Cuadro de revisiones"),
    LayerDef(NON_PLOT, 9, 25, "CONTINUOUS", "Geometría auxiliar que no se imprime", plot=False),
)

LAYER_NAMES: frozenset[str] = frozenset(layer.name for layer in LAYERS)
