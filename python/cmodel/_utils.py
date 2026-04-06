from collections.abc import Callable
from collections.abc import Collection
from struct import calcsize
from typing import TYPE_CHECKING
from typing import Any
from typing import TypedDict
from typing import get_args

from copier import Literal
from pydantic_core import core_schema as cs

if TYPE_CHECKING:
    from cmodel.base import CModel
    from cmodel.schema import CStructFieldSchema


type Prefix = Literal["@", "=", "<", ">", "!"]  # noqa: F722
"""A type for valid struct format string prefixes."""
PREFIXES = set(get_args(Prefix))
"""A set of valid struct format string prefixes."""


class PydanticCFormatMetadata[T](TypedDict):
    format: str
    """The format for this field compiled for each endian."""
    validate: Callable[[tuple[Any, ...]], T]
    """A function to convert the raw tuple produced by `struct.unpack` into a Python value."""
    dump: Callable[[T], tuple[Any, ...]]
    """A function to convert a Python value into a tuple that can be passed to `struct.pack`."""


class PydanticCRawMetadata[T](TypedDict):
    size: int | None
    """The size of the bytes field. None is variable-length."""
    alignment: int
    """The alignment of the bytes field."""
    validate: Callable[[bytes], T]
    """A function to convert raw bytes into a Python value."""
    dump: Callable[[T], bytes]
    """A function to convert a Python value into raw bytes."""


class PydanticMetadata(TypedDict, total=False):
    """Metadata for a Pydantic schema to control how it is converted to a CModel schema."""

    c_format: PydanticCFormatMetadata
    c_raw: PydanticCRawMetadata


def get_pydantic_metadata(schema: cs.CoreSchema) -> PydanticMetadata | None:
    """Get the CModel metadata from a Pydantic core schema, if it exists."""
    return schema.get("metadata", {}).get(PYDANTIC_SCHEMA_METADATA_KEY)


def set_pydantic_metadata(schema: cs.CoreSchema, metadata: PydanticMetadata) -> None:
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


def get_c_format_prefix(cls: type["CModel"]) -> Prefix:
    """Get the format prefix for the given endianness and size."""
    match (cls.c_endian_type, cls.c_size_type):
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
            msg = f"Invalid combination of endian_type {e} and size_type {s} for {cls}."
            raise ValueError(msg)
