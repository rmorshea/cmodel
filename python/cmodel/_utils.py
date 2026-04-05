from collections.abc import Collection
from struct import Struct
from struct import calcsize
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict

from pydantic_core import core_schema as cs

if TYPE_CHECKING:
    from cmodel.schema import CFormatByEndian
    from cmodel.schema import CFormatSchema
    from cmodel.schema import CStructFieldSchema


class PydanticSchemaMetadata(TypedDict, total=False):
    """Metadata for a Pydantic schema to control how it is converted to a CModel schema."""

    format_schema: "CFormatSchema[Any]"


def get_pydantic_schema_metadata(schema: cs.CoreSchema) -> PydanticSchemaMetadata:
    """Get the CModel metadata from a Pydantic core schema, if it exists."""
    return schema.get("metadata", {}).get(PYDANTIC_SCHEMA_METADATA_KEY, {})


PYDANTIC_SCHEMA_METADATA_KEY = "cmodel"


def get_format_alignment(fmt: str) -> int:
    """Return the size and character of the most strictly aligned type in a C format string."""
    size = 0
    for new_char in fmt:
        if (new_char.isalpha() or new_char == "?") and (new_size := calcsize(new_char)) > size:
            size = new_size
    if size == 0:
        msg = f"Format string {fmt} does not contain any valid format characters"
        raise ValueError(msg)
    return size


def get_field_schema_alignment(field_schemas: Collection["CStructFieldSchema"]) -> int:
    """Calculate the alignment of a struct from the alignments of its fields."""
    return max((f["schema"]["alignment"] for f in field_schemas), default=1)


def identity(x: Any) -> Any:
    return x


def compile_format_by_endian(fmt: str) -> "CFormatByEndian":
    """Compile a format string into a CFormatByEndian with Struct objects for each endianness."""
    return {endian: Struct(endian + fmt) for endian in ("=", "<", ">", "!")}
