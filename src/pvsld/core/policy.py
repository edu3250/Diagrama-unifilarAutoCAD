"""Design policy defaults that are choices of the project, not of NOM or CFE (basis ``POL``).

The numbers live here, in one place, so the rule pack (STR-007) and the sizing engine read the
same thresholds. A caller that needs different ones passes its own :class:`DcAcPolicy`.

> [!warning] Owner decision
> The DC/AC ratio thresholds are project policy, not regulation (vault note "PV SLD Validation
> Rules", section "Rule pack gap: inverter DC power"). The defaults below are proposals until the
> owner confirms them: a warning above 1.35 and an error above 1.50. The inverter datasheet limit
> on the PV array power (STR-007, ``pdc_max_w``) is applied separately and is always an error.

Example::

    policy = DcAcPolicy(warn_above=1.30, error_above=1.40)
    policy.classify(1.47)  # Severity.ERROR
"""

from __future__ import annotations

from dataclasses import dataclass

from pvsld.core.severity import Severity

DEFAULT_DC_AC_WARN_ABOVE = 1.35
"""DC/AC ratio above which STR-007 warns (vault note: project-policy ceiling of 1.35)."""
DEFAULT_DC_AC_ERROR_ABOVE = 1.50
"""DC/AC ratio above which STR-007 fails (owner proposal 2026-10-07: 1.50)."""
DEFAULT_DC_AC_INFO_BELOW = 1.0
"""DC/AC ratio below which STR-007 reports an informative finding (undersized array)."""


@dataclass(frozen=True)
class DcAcPolicy:
    """Thresholds on the DC/AC ratio (array STC power / inverter rated AC power).

    ``classify`` returns ``ERROR`` strictly above ``error_above``, ``WARNING`` strictly above
    ``warn_above``, ``INFO`` strictly below ``info_below`` and ``None`` otherwise.
    """

    warn_above: float = DEFAULT_DC_AC_WARN_ABOVE
    error_above: float = DEFAULT_DC_AC_ERROR_ABOVE
    info_below: float = DEFAULT_DC_AC_INFO_BELOW

    def __post_init__(self) -> None:
        if not 0 < self.info_below <= self.warn_above <= self.error_above:
            raise ValueError(
                "DC/AC policy needs 0 < info_below <= warn_above <= error_above, got "
                f"{self.info_below:g}, {self.warn_above:g}, {self.error_above:g}"
            )

    def classify(self, ratio: float) -> Severity | None:
        """Severity of ``ratio`` under this policy, ``None`` when it is within bounds."""
        if ratio > self.error_above:
            return Severity.ERROR
        if ratio > self.warn_above:
            return Severity.WARNING
        if ratio < self.info_below:
            return Severity.INFO
        return None


DEFAULT_DC_AC_POLICY = DcAcPolicy()
