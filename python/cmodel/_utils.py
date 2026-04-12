from collections.abc import Collection
from struct import calcsize
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict
from typing import get_args

from copier import Literal
from pydantic_core import core_schema as cs

if TYPE_CHECKING:
    from cmodel.base import CEncoded
    from cmodel.base import CFormat
    from cmodel.schema import CStructFieldSchema
    from cmodel.schema import EndianType
    from cmodel.schema import SizeType


type Prefix = Literal["@", "=", "<", ">", "!"]  # noqa: F722
"""A type for valid struct format string prefixes."""
PREFIXES = set(get_args(Prefix))
"""A set of valid struct format string prefixes."""


class PydanticSchemaMetadata[T](TypedDict, total=False):
    """Metadata for a Pydantic schema to control how it is converted to a CModel schema."""

    c_encoded: "CEncoded[T]"
    """The CEncoded metadata for this schema, if it exists."""
    c_format: "CFormat[T]"
    """The CFormat metadata for this schema, if it exists."""


def get_pydantic_schema_metadata(schema: cs.CoreSchema) -> PydanticSchemaMetadata | None:
    """Get the CModel metadata from a Pydantic core schema, if it exists."""
    return schema.get("metadata", {}).get(PYDANTIC_SCHEMA_METADATA_KEY)


def set_pydantic_schema_metadata(schema: cs.CoreSchema, metadata: PydanticSchemaMetadata) -> None:
    """Set the CModel metadata on a Pydantic core schema."""
    schema.setdefault("metadata", {})[PYDANTIC_SCHEMA_METADATA_KEY] = metadata


PYDANTIC_SCHEMA_METADATA_KEY = "cmodel"


def get_format_alignment(prefix: Prefix, fmt: str) -> int:
    """Return the size and character of the most strictly aligned type in a C format string."""
    size = 0
    for new_char in fmt:
        if (new_char.isalpha() or new_char == "?") and (
            new_size := calcsize(prefix + new_char)
        ) > size:
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


def get_c_format_prefix(
    endian_type: "EndianType",
    size_type: "SizeType",
    error_msg: str,
) -> Prefix:
    """Get the format prefix for the given endianness and size."""
    match (endian_type, size_type):
        case ("native", "native"):
            return "@"
        case ("native", "standard"):
            return "="
        case ("little", "standard"):
            return "<"
        case ("big", "standard"):
            return ">"
        case ("network", "standard"):
            return "!"
        case (e, s):
            msg = f"Invalid combination of endian_type {e} and size_type {s}{error_msg}"
            raise ValueError(msg)
