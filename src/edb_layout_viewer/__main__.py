# Copyright (C) 2023 - 2026 Contributors.
# SPDX-License-Identifier: Apache-2.0

"""Allow ``python -m edb_layout_viewer``."""

from __future__ import annotations

import sys

from edb_layout_viewer.cli import main

if __name__ == "__main__":
    sys.exit(main())
