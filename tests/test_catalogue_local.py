"""Stage 3.6.3: the user's local catalogue, merged with the bundled records.

The new equipment is the sample module of the fixtures under another name (ACME-AX-550), as if
Claude had read it from a datasheet; the local folder is a temporary one (see conftest.py).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from mcp.server.mcpserver.exceptions import ToolError

from pvsld.catalogue.errors import CatalogueError
from pvsld.catalogue.local import (
    DATASHEETS_FOLDER,
    LOCAL_REVIEWER,
    add_local_record,
    load_catalogue,
    local_catalogue_dir,
)
from pvsld.cli import main
from pvsld.mcp.catalogue_tool import datasheet_path, record_examples, run_add_component
from pvsld.mcp.sandbox import OutputSandbox
from pvsld.mcp.server import RECORD_EXAMPLES_URI, create_server
from pvsld.sizing import request_from_mapping, size_pv_system
from sizing_helpers import FIXTURE_RECORDS, template
from test_mcp_server import call, run_client, text_of

TODAY = date(2026, 10, 9)
NEW_ID = "ACME-AX-550"
PDF = b"%PDF-1.7\n% hoja tecnica de prueba\n"


def new_record() -> dict[str, Any]:
    """What Claude would extract: a whole record, ``source`` with only what it read."""
    data = yaml.safe_load((FIXTURE_RECORDS / "modules" / "xm-550.yaml").read_text(encoding="utf-8"))
    data["family_id"] = data["model_family"] = NEW_ID
    data["manufacturer"] = "Acme Solar"
    data["variants"][0]["component_id"] = NEW_ID
    data["source"] = {"title": "Acme AX-550 datasheet, rev. 2", "pages": [1, 2]}
    return data


@pytest.fixture
def local(tmp_path: Path) -> Path:
    folder = tmp_path / "catalogo"
    (folder / DATASHEETS_FOLDER).mkdir(parents=True)
    (folder / DATASHEETS_FOLDER / "acme.pdf").write_bytes(PDF)
    return folder


def _add(local: Path, data: dict[str, Any] | None = None, **options: Any) -> Any:
    registry = load_catalogue(FIXTURE_RECORDS, local=local)
    return add_local_record(
        data or new_record(),
        local,
        datasheet=local / DATASHEETS_FOLDER / "acme.pdf",
        registry=registry,
        today=TODAY,
        **options,
    )


# --- folder ---------------------------------------------------------------------------------------


def test_the_local_folder_follows_the_environment(tmp_path: Path) -> None:
    assert local_catalogue_dir({"PVSLD_LOCAL_CATALOGUE_DIR": str(tmp_path)}) == tmp_path
    windows = local_catalogue_dir({"APPDATA": r"C:\Users\ana\AppData\Roaming"})
    assert windows == Path(r"C:\Users\ana\AppData\Roaming") / "pvsld" / "catalogo"
    assert local_catalogue_dir({"XDG_DATA_HOME": "/home/ana/.data"}) == Path(
        "/home/ana/.data/pvsld/catalogo"
    )


# --- adding ---------------------------------------------------------------------------------------


def test_a_confirmed_record_is_written_and_merged(local: Path) -> None:
    added = _add(local)
    assert added.component_ids == (NEW_ID,)
    assert added.path == local / "modules" / "acme-ax-550.yaml"
    written = yaml.safe_load(added.path.read_text(encoding="utf-8"))
    source = written["source"]
    assert source["filename"] == "acme.pdf"
    assert len(source["sha256"]) == 64
    assert source["pages"] == [1, 2]
    assert (source["reviewed_by"], source["review_date"]) == (LOCAL_REVIEWER, TODAY)
    registry = load_catalogue(FIXTURE_RECORDS, local=local)
    assert NEW_ID in registry
    assert registry.is_local(NEW_ID)
    assert not registry.is_local("XM-550")
    assert registry.local_problems == ()


def test_the_new_module_can_be_sized(local: Path) -> None:
    _add(local)
    registry = load_catalogue(FIXTURE_RECORDS, local=local)
    request = request_from_mapping(
        {
            "module": NEW_ID,
            "template": template(),
            **{"module_count_min": 14, "module_count_max": 14},
        }
    )
    assert size_pv_system(request, registry).selected is not None


def test_an_id_of_the_bundled_catalogue_is_refused(local: Path) -> None:
    data = new_record()
    data["variants"][0]["component_id"] = "XM-550"
    with pytest.raises(CatalogueError, match="XM-550 is already in the catalogue"):
        _add(local, data)


def test_a_local_record_is_replaced_only_with_overwrite(local: Path) -> None:
    _add(local)
    with pytest.raises(CatalogueError, match="local catalogue"):
        _add(local)
    assert _add(local, overwrite=True).component_ids == (NEW_ID,)


def test_an_invalid_record_lists_its_problems(local: Path) -> None:
    data = new_record()
    del data["variants"][0]["voc_v"]
    data["variants"][0]["vmp_v"] = 80.0
    with pytest.raises(CatalogueError) as caught:
        _add(local, data)
    text = "; ".join(caught.value.problems)
    assert "voc_v" in text
    assert not (local / "modules").exists()


def test_the_datasheet_must_exist(local: Path) -> None:
    with pytest.raises(CatalogueError, match="datasheet not found"):
        add_local_record(
            new_record(),
            local,
            datasheet=local / DATASHEETS_FOLDER / "no.pdf",
            registry=load_catalogue(FIXTURE_RECORDS, local=local),
        )


# --- loading --------------------------------------------------------------------------------------


def test_a_broken_or_clashing_local_record_is_left_out_not_fatal(local: Path) -> None:
    (local / "modules").mkdir()
    (local / "modules" / "roto.yaml").write_text("component_type: pv_module\n", encoding="utf-8")
    clash = (FIXTURE_RECORDS / "modules" / "xm-550.yaml").read_text(encoding="utf-8")
    (local / "modules" / "xm-550.yaml").write_text(clash, encoding="utf-8")
    registry = load_catalogue(FIXTURE_RECORDS, local=local)
    assert "XM-550" in registry
    assert not registry.is_local("XM-550")
    problems = " ".join(registry.local_problems)
    assert "roto.yaml" in problems
    assert "XM-550 is already in the catalogue" in problems


def test_without_a_local_folder_the_bundled_catalogue_is_unchanged(tmp_path: Path) -> None:
    registry = load_catalogue(FIXTURE_RECORDS, local=tmp_path / "no-existe")
    assert registry.local_ids == frozenset()
    assert len(registry) == len(load_catalogue(FIXTURE_RECORDS))


# --- MCP ------------------------------------------------------------------------------------------


def test_the_tool_needs_the_users_confirmation(local: Path) -> None:
    registry = load_catalogue(FIXTURE_RECORDS, local=local)
    with pytest.raises(ToolError, match="user_confirmed=true"):
        run_add_component(
            registry,
            local,
            record=new_record(),
            datasheet="acme.pdf",
            user_confirmed=False,
            overwrite=False,
        )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("../acme.pdf", "not a path"),
        ("C:\\otro\\acme.pdf", "not a path"),
        ("acme.txt", "PDF"),
        ("falta.pdf", "Copy the user's datasheet"),
    ],
)
def test_the_datasheet_is_a_file_name_in_the_local_folder(
    local: Path, name: str, message: str
) -> None:
    with pytest.raises(ToolError, match=message):
        datasheet_path(local, name)


def test_add_component_through_an_mcp_client(local: Path, tmp_path: Path) -> None:
    server = create_server(
        OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS, local_catalogue=local
    )
    arguments = {"record": json.loads(json.dumps(new_record())), "datasheet": "acme.pdf"}
    result = call(server, "add_component_to_catalogue", {**arguments, "user_confirmed": True})
    assert not result.is_error, text_of(result)
    assert result.structured_content is not None
    assert result.structured_content["component_ids"] == [NEW_ID]
    listed = call(server, "list_components", {"component_type": "pv_module"})
    assert f"{NEW_ID}  pv_module  Acme Solar" in text_of(listed)
    assert "LOCAL" in text_of(listed)
    rows = {c["component_id"]: c for c in listed.structured_content["components"]}  # type: ignore[index]
    assert rows[NEW_ID]["local"] is True
    assert rows["XM-550"]["local"] is False


def test_the_record_examples_cover_every_type(local: Path) -> None:
    data = record_examples(FIXTURE_RECORDS, local)
    assert data["datasheets_folder"] == str(local / DATASHEETS_FOLDER)
    assert {"pv_module", "string_inverter", "dc_fuse", "dc_breaker"} <= set(data["examples"])
    assert "component_type: pv_module" in data["examples"]["pv_module"]


def test_the_examples_are_a_resource(local: Path, tmp_path: Path) -> None:
    server = create_server(
        OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS, local_catalogue=local
    )
    contents = run_client(server, lambda client: client.read_resource(RECORD_EXAMPLES_URI))
    data = json.loads(contents.contents[0].text)  # type: ignore[union-attr]
    assert "pv_module" in data["examples"]


# --- CLI ------------------------------------------------------------------------------------------


def test_pvsld_catalogue_add_and_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    local = tmp_path / "catalogo"
    monkeypatch.setenv("PVSLD_LOCAL_CATALOGUE_DIR", str(local))
    record = tmp_path / "acme.yaml"
    record.write_text(yaml.safe_dump(new_record(), allow_unicode=True), encoding="utf-8")
    pdf = tmp_path / "Acme AX-550.pdf"
    pdf.write_bytes(PDF)
    argv = ["catalogue", "add", str(record), "--datasheet", str(pdf)]
    assert main([*argv, "--records", str(FIXTURE_RECORDS)]) == 0
    assert "added ACME-AX-550" in capsys.readouterr().out
    assert (local / DATASHEETS_FOLDER / "Acme AX-550.pdf").read_bytes() == PDF
    assert (
        main(["catalogue", "list", "--records", str(FIXTURE_RECORDS), "--type", "pv_module"]) == 0
    )
    row = next(line for line in capsys.readouterr().out.splitlines() if NEW_ID in line)
    assert row.rstrip().endswith("local")
