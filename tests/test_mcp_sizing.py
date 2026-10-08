"""Stage 3.5: the catalogue and sizing tools of the MCP server, through a real MCP client.

The server reads the fixture catalogue (copies of the owner's records and the sample pair), so the
results do not change when the owner adds datasheets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pvsld.mcp.sandbox import OutputSandbox
from pvsld.mcp.server import RULEPACK_URI, SIZING_TEMPLATE_URI, create_server
from pvsld.mcp.sizing_tools import (
    CATALOGUE_DIR_ENV,
    MAX_ALTERNATIVES,
    catalogue_dir_from_environment,
)
from pvsld.sizing.models import REQUIRED_TEMPLATE_KEYS
from sizing_helpers import ET_550, FIXTURE_RECORDS, GROWATT_5K, HUAWEI_5K, JINKO_650
from test_mcp_server import call, estimated_tokens, example_spec, run_client, text_of

SIZING_BUDGET_TOKENS = 8_000
RULEPACK_BUDGET_TOKENS = 15_000


@pytest.fixture
def server(tmp_path: Path) -> Any:
    return create_server(OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS)


def template() -> dict[str, Any]:
    spec = example_spec()
    return {key: spec[key] for key in REQUIRED_TEMPLATE_KEYS}


def size(server: Any, **arguments: Any) -> Any:
    return call(server, "size_pv_system", {"template": template(), **arguments})


# --- catalogue ------------------------------------------------------------------------------------


def test_list_components_filters_by_type_and_manufacturer(server: Any) -> None:
    modules = call(server, "list_components", {"component_type": "pv_module"})
    data = modules.structured_content
    assert data is not None
    assert data["ok"] is True
    assert data["count"] == len(data["components"]) > 0
    assert {c["component_type"] for c in data["components"]} == {"pv_module"}
    assert ET_550 in {c["component_id"] for c in data["components"]}
    assert f"{ET_550}  pv_module" in text_of(modules)
    huawei = call(server, "list_components", {"manufacturer": "huawei"}).structured_content
    assert huawei is not None
    assert {c["manufacturer"] for c in huawei["components"]} == {"Huawei"}
    assert HUAWEI_5K in {c["component_id"] for c in huawei["components"]}


def test_get_component_returns_the_datasheet_values_and_their_provenance(server: Any) -> None:
    result = call(server, "get_component", {"component_id": GROWATT_5K})
    data = result.structured_content
    assert data is not None
    assert (data["component_id"], data["component_type"]) == (GROWATT_5K, "string_inverter")
    source = data["data"]["source"]
    assert len(source["sha256"]) == 64
    assert "reviewed_by" in source
    assert data["data"]["rated_ac_power_w"] == 5000


def test_an_unknown_component_is_a_tool_error_with_suggestions(server: Any) -> None:
    result = call(server, "get_component", {"component_id": "GROWATT-MIN-5000TL"})
    assert result.is_error
    assert GROWATT_5K in text_of(result)


# --- sizing ---------------------------------------------------------------------------------------


def test_size_returns_a_spec_that_validates_and_draws(server: Any) -> None:
    result = size(server, module=ET_550, inverters=[GROWATT_5K], target_dc_power_w=9000)
    assert not result.is_error
    data = result.structured_content
    assert data is not None
    assert data["ok"] is True
    assert data["summary"].startswith(f"SELECTED: {GROWATT_5K} 2")
    assert data["selected"]["inverter"] == GROWATT_5K
    spec = data["spec"]
    assert spec["layout"]["template"] == "a3_plantilla_v1"
    assert len(data["alternatives"]) <= MAX_ALTERNATIVES
    assert {"rule_id", "count", "inverters", "example_es"} <= set(data["rejected"][0])
    assert "SELECTED:" in text_of(result)
    validated = call(server, "validate_pv_design", {"spec": spec}).structured_content
    assert validated is not None
    assert validated["ok"] is True
    drawn = call(
        server, "generate_single_line_diagram", {"spec": spec, "preview": False, "name": "et"}
    )
    assert not drawn.is_error
    assert drawn.structured_content is not None
    assert drawn.structured_content["readback"]["ok"] is True


def test_no_candidate_is_a_normal_result_that_names_the_rules(server: Any) -> None:
    result = size(server, module=JINKO_650, inverters=[HUAWEI_5K], target_dc_power_w=6500)
    assert not result.is_error
    data = result.structured_content
    assert data is not None
    assert data["ok"] is False
    assert "spec" not in data
    assert data["summary"].startswith("NO CANDIDATE")
    assert "STR-004" in {row["rule_id"] for row in data["rejected"]}
    assert all(row["example_es"] for row in data["rejected"])
    assert "STR-004" in text_of(result)


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        ({"module": "NOPE-1", "inverters": [GROWATT_5K]}, "NOPE-1"),
        ({"module": GROWATT_5K, "inverters": [GROWATT_5K]}, "not a PVModule"),
    ],
)
def test_a_bad_request_is_a_tool_error_that_says_why(
    server: Any, arguments: dict[str, Any], fragment: str
) -> None:
    result = size(server, **arguments)
    assert result.is_error
    assert fragment in text_of(result)


def test_a_template_without_its_sections_is_refused(server: Any) -> None:
    result = call(
        server,
        "size_pv_system",
        {"template": {"project": template()["project"]}, "module": ET_550},
    )
    assert result.is_error
    assert "template lacks" in text_of(result)


# --- budgets and resources ----------------------------------------------------------------------


def test_a_sizing_result_stays_within_its_token_budget(server: Any) -> None:
    result = size(server, module=ET_550, inverters="auto", target_dc_power_w=9000)
    assert estimated_tokens(result) <= SIZING_BUDGET_TOKENS


def test_the_rule_pack_resource_stays_within_its_token_budget(server: Any) -> None:
    contents = run_client(server, lambda client: client.read_resource(RULEPACK_URI)).contents
    assert len(contents[0].text) / 4 <= RULEPACK_BUDGET_TOKENS  # type: ignore[union-attr]


def test_the_sizing_template_resource_has_every_section_on_the_owner_sheet(server: Any) -> None:
    contents = run_client(server, lambda c: c.read_resource(SIZING_TEMPLATE_URI)).contents
    sections = json.loads(contents[0].text)  # type: ignore[union-attr]
    assert set(sections) == set(REQUIRED_TEMPLATE_KEYS)
    assert sections["layout"]["template"] == "a3_plantilla_v1"
    assert "modules" not in sections


def test_the_catalogue_defaults_to_the_repository_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CATALOGUE_DIR_ENV, raising=False)
    default = catalogue_dir_from_environment()
    assert default.parts[-2:] == ("datasheets", "records")
    assert default.is_dir()
    monkeypatch.setenv(CATALOGUE_DIR_ENV, "D:/otro/catalogo")
    assert catalogue_dir_from_environment() == Path("D:/otro/catalogo")
