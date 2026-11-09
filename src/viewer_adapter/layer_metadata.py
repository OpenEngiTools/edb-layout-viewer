# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Stackup layer metadata used during scene capture."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from viewer_adapter.diagnostics import _record_exception

if TYPE_CHECKING:
    from pyedb.grpc.edb import Edb


def _conductor_names(edb: Edb, layout_layers: dict[str, Any] | None = None) -> tuple[str, ...]:
    """Use stackup order/types, never conventional TOP/BOTTOM layer names.

    ``edb.stackup.layers`` fetches and wraps every stackup layer from the EDB
    server, so callers that already hold that dictionary should pass it in
    via ``layout_layers`` instead of triggering another round of server calls.
    """
    signals = set(edb.stackup.signal_layers)
    layers = edb.stackup.layers if layout_layers is None else layout_layers
    return tuple(
        name
        for name, layer in layers.items()
        if name in signals or getattr(layer, "type", None) in {"signal", "conducting"}
    )


def _component_sides(edb: Edb, diagnostics: list[str], layout_layers: dict[str, Any] | None = None) -> dict[str, str]:
    layout_layers = edb.stackup.layers if layout_layers is None else layout_layers
    names = _conductor_names(edb, layout_layers)
    if not names:
        return {}
    sides = {names[0]: "top"}
    if len(names) > 1:
        sides[names[-1]] = "bottom"
    else:
        # A single conductor can explicitly belong to the back surface. If no
        # association is supplied, the sole layer is the front of the stackup.
        core = getattr(layout_layers[names[0]], "core", None)
        if core is not None:
            try:
                association = getattr(core, "top_bottom_association", None)
                if getattr(association, "name", None) == "BOTTOM_ASSOCIATED":
                    sides[names[0]] = "bottom"
            except Exception as exc:  # noqa: BLE001
                _record_exception(
                    diagnostics, f"Layer {names[0]}: side association unavailable ({exc}); using stackup order.", exc
                )
    return sides
