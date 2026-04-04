from collections.abc import Collection
from struct import calcsize
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from cmodel.schema import CStructFieldSchema


def calc_format_alignment(fmt: str) -> int:
    """Calculate the alignment of a C format string."""
    return max((calcsize(f) for f in fmt if f.isalpha()), default=0)


def calc_struct_alignment(field_schemas: Collection["CStructFieldSchema"]) -> int:
    """Calculate the alignment of a struct as the max alignment of its fields."""
    return max((f["schema"]["alignment"] for f in field_schemas), default=0)


def identity(x: Any) -> Any:
    return x
