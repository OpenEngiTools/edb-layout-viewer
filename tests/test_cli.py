# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

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

    assert cli.main([str(design), "--edbversion", "2025.1", "--layers", "TOP"]) == 0
    assert opened["args"] == (design, "2025.1")
    assert launched["edb"] == "EDB"
    assert launched["layers"] == ["TOP"]
    assert launched["nets"] is None
    assert launched["block"] is True


def test_main_rejects_missing_design(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main([str(tmp_path / "missing.aedb")])

    assert excinfo.value.code == 2
    assert "design directory not found" in capsys.readouterr().err
