# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from edb_layout_viewer import cli


def test_parser_accepts_repeated_and_multi_value_options():
    args = cli.build_parser().parse_args(
        ["design.aedb", "--layers", "TOP", "BOTTOM", "--layers", "GND", "--nets", "VCC", "--backend", "vulkan"]
    )

    assert args.design == Path("design.aedb")
    assert args.layers == ["TOP", "BOTTOM", "GND"]
    assert args.nets == ["VCC"]
    assert args.backend == "vulkan"
    assert args.debug is False
    assert args.live is False


def test_main_opens_design_and_blocks_in_viewer(tmp_path, monkeypatch):
    design = tmp_path / "board.aedb"
    design.mkdir()
    opened = {}
    launched = {}

    def fake_open(path, edbversion):
        opened["args"] = (path, edbversion)
        return "EDB"

    def fake_launch(edb, **kwargs):
        launched["edb"] = edb
        launched.update(kwargs)

    monkeypatch.setattr(cli, "_open_edb", fake_open)
    monkeypatch.setattr(cli, "launch_viewer", fake_launch)
    monkeypatch.setattr(cli, "_select_edb_file", Mock(side_effect=AssertionError("unexpected file dialog")))

    assert cli.main([str(design), "--edbversion", "2025.1", "--layers", "TOP"]) == 0
    assert opened["args"] == (design, "2025.1")
    assert launched["edb"] == "EDB"
    assert launched["layers"] == ["TOP"]
    assert launched["nets"] is None
    assert launched["block"] is True
    assert launched["live"] is False


def test_main_passes_live_flag_values(tmp_path, monkeypatch):
    design = tmp_path / "board.aedb"
    design.mkdir()
    launched = {}
    monkeypatch.setattr(cli, "_open_edb", lambda path, edbversion: "EDB")
    monkeypatch.setattr(cli, "launch_viewer", lambda edb, **kwargs: launched.update(kwargs))

    assert cli.main([str(design), "--live", "False"]) == 0
    assert launched["live"] is False
    assert cli.main([str(design), "--live"]) == 0
    assert launched["live"] is True
    assert cli.main([str(design), "--live", "0"]) == 0
    assert launched["live"] is False


def test_parser_rejects_invalid_live_value():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["design.aedb", "--live", "maybe"])


def test_main_rejects_missing_design(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main([str(tmp_path / "missing.aedb")])

    assert excinfo.value.code == 2
    assert "design directory not found" in capsys.readouterr().err


def test_parser_allows_omitted_design():
    args = cli.build_parser().parse_args(["--edbversion", "2025.1"])

    assert args.design is None
    assert args.edbversion == "2025.1"


def test_main_opens_selected_edb_file(tmp_path, monkeypatch):
    design = tmp_path / "board.aedb"
    design.mkdir()
    selected = design / "edb.def"
    selected.touch()
    open_edb = Mock(return_value="EDB")
    launch = Mock()
    monkeypatch.setattr(cli, "_select_edb_file", lambda: selected)
    monkeypatch.setattr(cli, "_open_edb", open_edb)
    monkeypatch.setattr(cli, "launch_viewer", launch)

    assert cli.main(["--edbversion", "2025.1", "--layers", "TOP", "--live", "false"]) == 0

    open_edb.assert_called_once_with(design, "2025.1")
    launch.assert_called_once_with("EDB", layers=["TOP"], nets=None, backend=None, live=False, debug=False, block=True)


def test_main_exits_when_file_dialog_is_cancelled(monkeypatch):
    open_edb = Mock()
    launch = Mock()
    monkeypatch.setattr(cli, "_select_edb_file", lambda: None)
    monkeypatch.setattr(cli, "_open_edb", open_edb)
    monkeypatch.setattr(cli, "launch_viewer", launch)

    assert cli.main([]) == 0

    open_edb.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("selection", ["missing/edb.def", "other.def", "edb.def"])
def test_main_rejects_invalid_file_selection(tmp_path, monkeypatch, capsys, selection):
    selected = tmp_path / selection
    if selection == "other.def":
        selected.touch()
    elif selection == "edb.def":
        selected.mkdir()
    open_edb = Mock()
    launch = Mock()
    monkeypatch.setattr(cli, "_select_edb_file", lambda: selected)
    monkeypatch.setattr(cli, "_open_edb", open_edb)
    monkeypatch.setattr(cli, "launch_viewer", launch)

    with pytest.raises(SystemExit) as excinfo:
        cli.main([])

    assert excinfo.value.code == 2
    assert "select an existing edb.def file" in capsys.readouterr().err
    open_edb.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("filename", ["", "board.aedb/edb.def"])
def test_select_edb_file_initializes_qt_and_uses_file_filter(monkeypatch, filename):
    get_application = Mock(return_value=(object(), True))
    dialog = Mock(return_value=(filename, "EDB definition (edb.def)"))
    monkeypatch.setitem(sys.modules, "layout_viewer_core.qt.app", SimpleNamespace(_get_application=get_application))
    monkeypatch.setitem(
        sys.modules, "PySide6.QtWidgets", SimpleNamespace(QFileDialog=SimpleNamespace(getOpenFileName=dialog))
    )

    assert cli._select_edb_file() == (Path(filename) if filename else None)

    get_application.assert_called_once_with()
    dialog.assert_called_once_with(None, "Select EDB design", "", "EDB definition (edb.def)")
