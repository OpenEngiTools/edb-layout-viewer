# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Scene capture filter normalization."""

from collections.abc import Iterable


def normalize_names(value: str | Iterable[str] | None) -> set[str] | None:
    return None if value is None else {value} if isinstance(value, str) else set(value)
