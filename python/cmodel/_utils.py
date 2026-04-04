from collections.abc import Collection
from struct import calcsize
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict

from pydantic_core import core_schema as cs

if TYPE_CHECKING:
    from cmodel.schema import CFormatSchema
    from cmodel.schema import CStructFieldSchema


class PydanticSchemaMetadata(TypedDict, total=False):
    """Metadata for a Pydantic schema to control how it is converted to a CModel schema."""

    format_schema: "CFormatSchema[Any]"


def get_pydantic_schema_metadata(schema: cs.CoreSchema) -> PydanticSchemaMetadata:
    """Get the CModel metadata from a Pydantic core schema, if it exists."""
    return schema.get("metadata", {}).get(PYDANTIC_SCHEMA_METADATA_KEY, {})


PYDANTIC_SCHEMA_METADATA_KEY = "cmodel"


def calc_format_alignment(fmt: str) -> int:
    """Calculate the alignment of a C format string."""
    return max((calcsize(f) for f in fmt if f.isalpha()), default=0)


def calc_struct_alignment(field_schemas: Collection["CStructFieldSchema"]) -> int:
    """Calculate the alignment of a struct as the max alignment of its fields."""
    return max((f["schema"]["alignment"] for f in field_schemas), default=0)


def identity(x: Any) -> Any:
    return x
