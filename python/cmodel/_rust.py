import os
from typing import Any

lib: Any
try:
    from cmodel import _lib as lib  # pyright: ignore[reportAttributeAccessIssue]
except ImportError:
    lib = None

__all__ = ["HAS_RUST", "USE_RUST", "lib"]

USE_RUST = os.environ.get("CMODEL_RUST", "1").lower() in ("1", "true")
HAS_RUST = lib is not None
