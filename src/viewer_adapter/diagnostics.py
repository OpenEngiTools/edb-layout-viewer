# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Shared exception logging and debug diagnostics helpers."""

from __future__ import annotations

import logging
import traceback

_logger = logging.getLogger(__name__)


class _Diagnostics(list):
    """A diagnostics list that also remembers whether debug mode is enabled."""

    def __init__(self, debug: bool = False) -> None:
        super().__init__()
        self.debug = debug


def _record_exception(diagnostics: list[str], message: str, exc: BaseException) -> None:
    """Record a caught exception.

    In normal mode, append only ``message`` and let the caller keep going
    (best-effort capture). In debug mode, additionally append the full
    traceback, log it, and re-raise so a debugger/pytest stops at the real
    failure. A marker on the exception prevents duplicate logging when it
    passes through nested ``except`` blocks on its way out.
    """
    if not getattr(diagnostics, "debug", False):
        diagnostics.append(message)
        return
    if not getattr(exc, "_viewer_diagnostics_logged", False):
        diagnostics.append(message)
        diagnostics.append(traceback.format_exc())
        _logger.exception(message)
        exc._viewer_diagnostics_logged = True
    raise exc
