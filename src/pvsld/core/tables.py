"""NOM-001-SEDE tables as data, keyed by edition.

Rules and calculations never hard-code a table value: they read an :class:`NomTables` obtained from
:func:`get_tables`. A new NOM-001-SEDE edition (a modification is scheduled for 2026, see ADR-0001,
driver D11) is therefore a new data object, not a code change.

> [!warning] Verify before real use
> The ampacity, correction-factor and rooftop-adder values follow the NEC-equivalent tables the
> vault notes cite (Table 310-15(b)(16), (b)(2)(a), (b)(3)(a), (b)(3)(c)) and are checked by the
> tests against the vault's worked examples. The conductor resistances (Chapter 10, Tables 8 and
> 9) and the NOM Table 690-7 factors must be re-read against the published NOM text before a
> design is issued. The conduit-fill data (Chapter 10, Tables 1, 4, 5 and 8) was read from the
> rendered pages of the published NOM on 2026-10-09; Table 5 is kept as diameters because its
> area column has misprints (10 AWG THHW reads 55.68 mm2 for a 4.470 mm diameter). This module
> belongs to a spike; drawings are drafts for the responsible engineer, never certified documents.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class NomTables:
    """Every table the calculations and the rule pack need, for one NOM-001-SEDE edition."""

    edition: str
    # Table 310-15(b)(16), copper: size -> ampacity (A) in the 60, 75 and 90 degC columns.
    ampacity_cu: Mapping[str, tuple[float, float, float]]
    # Table 310-15(b)(2)(a), 90 degC column (30 degC base): (highest ambient of the band, factor).
    temp_correction_90c: tuple[tuple[float, float], ...]
    # Table 310-15(b)(3)(a): (largest conductor count of the band, factor).
    bundling: tuple[tuple[int, float], ...]
    # Table 310-15(b)(3)(c), sunlit raceway on a roof: (largest clearance in mm, adder in degC).
    rooftop_adder_c: tuple[tuple[float, float], ...]
    # Table 690-7 (crystalline silicon): (lowest degC of the band, voltage correction factor).
    voc_table_690_7: tuple[tuple[float, float], ...]
    # 240-6(a): standard ratings of inverse-time breakers and fuses (A).
    standard_ocpd_a: tuple[float, ...]
    # 240-4(d): largest OCPD (A) that protects a small copper conductor.
    small_conductor_ocpd_limit_a: Mapping[str, float]
    # Chapter 10, Table 8: copper DC resistance (ohm/km).
    # Chapter 10, Table 9: copper AC resistance in PVC conduit (ohm/km).
    resistance_dc_ohm_km: Mapping[str, float]
    resistance_ac_pvc_ohm_km: Mapping[str, float]
    # Conductor cross-section (mm2), shown next to the AWG size on the sheet (MX-A04).
    awg_mm2: Mapping[str, float]
    # Chapter 10, Table 1: largest fill, % of the conduit area, for 1, 2 and more than 2 conductors.
    conduit_fill_pct: tuple[float, float, float]
    # Chapter 10, Table 4, article 358 (EMT): (metric designation mm, trade size, internal
    # diameter mm, total area mm2).
    emt: tuple[tuple[int, str, float, float], ...]
    # Chapter 10, Table 5, types TW, THHW, THW, THW-2: approximate overall diameter (mm).
    thhw_diameter_mm: Mapping[str, float]
    # Chapter 10, Table 8, stranded copper: overall area (mm2) of the bare conductor.
    bare_stranded_area_mm2: Mapping[str, float]


NOM_001_SEDE_2012 = NomTables(
    edition="NOM-001-SEDE-2012",
    ampacity_cu={
        "14 AWG": (20, 20, 25),
        "12 AWG": (25, 25, 30),
        "10 AWG": (30, 35, 40),
        "8 AWG": (40, 50, 55),
        "6 AWG": (55, 65, 75),
        "4 AWG": (70, 85, 95),
        "3 AWG": (85, 100, 115),
        "2 AWG": (95, 115, 130),
        "1 AWG": (110, 130, 145),
        "1/0 AWG": (125, 150, 170),
        "2/0 AWG": (145, 175, 195),
        "3/0 AWG": (165, 200, 225),
        "4/0 AWG": (195, 230, 260),
    },
    temp_correction_90c=(
        (10, 1.15),
        (15, 1.12),
        (20, 1.08),
        (25, 1.04),
        (30, 1.00),
        (35, 0.96),
        (40, 0.91),
        (45, 0.87),
        (50, 0.82),
        (55, 0.76),
        (60, 0.71),
        (65, 0.65),
        (70, 0.58),
        (75, 0.50),
        (80, 0.41),
        (85, 0.29),
    ),
    bundling=((3, 1.0), (6, 0.80), (9, 0.70), (20, 0.50), (30, 0.45), (40, 0.40)),
    rooftop_adder_c=((13, 33), (90, 22), (300, 17), (900, 14)),
    voc_table_690_7=(
        (20, 1.02),
        (15, 1.04),
        (10, 1.06),
        (5, 1.08),
        (0, 1.10),
        (-5, 1.12),
        (-10, 1.14),
        (-15, 1.16),
        (-20, 1.18),
        (-25, 1.20),
        (-30, 1.21),
        (-35, 1.23),
        (-40, 1.25),
    ),
    standard_ocpd_a=(
        15,
        20,
        25,
        30,
        35,
        40,
        45,
        50,
        60,
        70,
        80,
        90,
        100,
        110,
        125,
        150,
        175,
        200,
        225,
        250,
        300,
        350,
        400,
        450,
        500,
        600,
        700,
        800,
        1000,
        1200,
        1600,
        2000,
        2500,
        3000,
        4000,
        5000,
        6000,
    ),
    small_conductor_ocpd_limit_a={"14 AWG": 15, "12 AWG": 20, "10 AWG": 30},
    resistance_dc_ohm_km={
        "14 AWG": 10.2,
        "12 AWG": 6.50,
        "10 AWG": 4.07,
        "8 AWG": 2.55,
        "6 AWG": 1.61,
        "4 AWG": 1.01,
        "3 AWG": 0.802,
        "2 AWG": 0.634,
        "1 AWG": 0.505,
        "1/0 AWG": 0.399,
        "2/0 AWG": 0.317,
        "3/0 AWG": 0.2512,
        "4/0 AWG": 0.1991,
    },
    resistance_ac_pvc_ohm_km={
        "14 AWG": 10.2,
        "12 AWG": 6.6,
        "10 AWG": 3.9,
        "8 AWG": 2.56,
        "6 AWG": 1.61,
        "4 AWG": 1.02,
        "3 AWG": 0.82,
        "2 AWG": 0.66,
        "1 AWG": 0.52,
        "1/0 AWG": 0.39,
        "2/0 AWG": 0.33,
        "3/0 AWG": 0.25,
        "4/0 AWG": 0.203,
    },
    awg_mm2={
        "14 AWG": 2.08,
        "12 AWG": 3.31,
        "10 AWG": 5.26,
        "8 AWG": 8.37,
        "6 AWG": 13.3,
        "4 AWG": 21.2,
        "3 AWG": 26.7,
        "2 AWG": 33.6,
        "1 AWG": 42.4,
        "1/0 AWG": 53.5,
        "2/0 AWG": 67.4,
        "3/0 AWG": 85.0,
        "4/0 AWG": 107.2,
    },
    conduit_fill_pct=(53.0, 31.0, 40.0),
    emt=(
        (16, "½", 15.8, 196),
        (21, "¾", 20.9, 343),
        (27, "1", 26.6, 556),
        (35, "1¼", 35.1, 968),
        (41, "1½", 40.9, 1314),
        (53, "2", 52.5, 2165),
        (63, "2½", 69.4, 3783),
        (78, "3", 85.2, 5701),
        (91, "3½", 97.4, 7451),
        (103, "4", 110.1, 9521),
    ),
    thhw_diameter_mm={
        "14 AWG": 3.378,
        "12 AWG": 3.861,
        "10 AWG": 4.470,
        "8 AWG": 5.994,
        "6 AWG": 7.722,
        "4 AWG": 8.941,
        "3 AWG": 9.652,
        "2 AWG": 10.46,
        "1 AWG": 12.50,
        "1/0 AWG": 13.51,
        "2/0 AWG": 14.68,
        "3/0 AWG": 16.00,
        "4/0 AWG": 17.48,
    },
    bare_stranded_area_mm2={
        "14 AWG": 2.68,
        "12 AWG": 4.25,
        "10 AWG": 6.76,
        "8 AWG": 10.76,
        "6 AWG": 17.09,
        "4 AWG": 27.19,
        "3 AWG": 34.28,
        "2 AWG": 43.23,
        "1 AWG": 55.8,
        "1/0 AWG": 70.41,
        "2/0 AWG": 88.74,
        "3/0 AWG": 111.9,
        "4/0 AWG": 141.1,
    },
)

_EDITIONS: Mapping[str, NomTables] = {NOM_001_SEDE_2012.edition: NOM_001_SEDE_2012}


def get_tables(edition: str) -> NomTables:
    """Return the tables of a NOM-001-SEDE ``edition``.

    Raises:
        KeyError: no table set is available for that edition.
    """
    try:
        return _EDITIONS[edition]
    except KeyError:
        known = ", ".join(sorted(_EDITIONS))
        raise KeyError(f"no NOM tables for edition {edition!r} (available: {known})") from None
