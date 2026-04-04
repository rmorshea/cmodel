import operator
from collections.abc import Callable
from collections.abc import Collection
from struct import calcsize
from typing import Any
from typing import Literal
from typing import TypedDict
from typing import get_args

from pydantic_core import core_schema as cs

CORE_SCHEMA_TYPES = get_args(cs.CoreSchemaType)


class CFormatSchema[T](TypedDict):
    """A schema for a single field in a C struct."""

    type: Literal["format"]
    format: str
    alignment: int
    validate: Callable[[tuple[Any, ...]], T]
    dump: Callable[[T], tuple[Any, ...]]


class CStructFieldSchema(TypedDict):
    """A schema for a single field in a C struct."""

    type: Literal["struct-field"]
    schema: "CSchema"
    variable_length: bool


class CStructSchema(TypedDict):
    """A schema for a C struct."""

    type: Literal["struct"]

    field_schemas: dict[str, CStructFieldSchema]
    """The inner schemas for each field in the struct, keyed by field name."""
    alignment: int
    """The alignment of the struct, in bytes."""
    anonymous: bool
    """Anonymous structs become tuples instead of dicts when unpacked."""


CSchema = CStructSchema | CFormatSchema
"""Any C schema"""


def c_schema_from_pydantic_core_schema(core_schema: cs.CoreSchema) -> CSchema:
    """Convert a Pydantic core schema to a CModel schema."""
    fake_field_schema = CStructFieldSchema(
        type="struct-field",
        schema=None,  # pyright: ignore[reportArgumentType]
        variable_length=False,
    )
    _visit(core_schema, {"parent_field_schema": fake_field_schema})
    return fake_field_schema["schema"]


class _VisitorContext(TypedDict):
    """Context for the schema visitor."""

    parent_field_schema: CStructFieldSchema
    """The schema of the current field being visited."""


def _visit(py_schema: cs.CoreSchema, context: _VisitorContext) -> None:
    """Visitor function to convert a Pydantic core schema to a CModel schema."""
    match py_schema["type"]:
        case "model":
            c_schema = CStructSchema(
                type="struct",
                field_schemas={},
                alignment=0,
                anonymous=False,
            )

            parent_field_schema = context["parent_field_schema"]
            parent_field_schema["schema"] = c_schema

            _visit(py_schema["schema"], context)

            # Now that we've visited all the fields, we can calculate the struct's alignment as
            # the max alignment of its field alignments.
            c_schema["alignment"] = _calc_struct_alignment(c_schema["field_schemas"].values())
        case "model-fields":
            parent_schema = context["parent_field_schema"]["schema"]

            if parent_schema["type"] != "struct":
                msg = "model-fields schema can only be used inside a model schema"
                raise TypeError(msg)

            for f_name, py_f_schema in py_schema["fields"].items():
                c_f_schema = CStructFieldSchema(
                    type="struct-field",
                    # Will get filled in by the nested visit when we visit the field's schema
                    schema=None,  # pyright: ignore[reportArgumentType]
                    variable_length=py_f_schema.get("extra", {}).get("c_variable_length", False),
                )
                parent_schema["field_schemas"][f_name] = c_f_schema
                _visit(py_f_schema["schema"], {"parent_field_schema": c_f_schema})
        case "tuple":
            py_items_schema = py_schema["items_schema"]
            variadic_item_index = py_schema.get("variadic_item_index", -1)
            if variadic_item_index < 0 and variadic_item_index + 1 != len(py_items_schema):
                msg = "CModel does not support variadic tuples"
                raise ValueError(msg)

            # Tuples are treated as anonymous structs
            c_schema = CStructSchema(
                type="struct",
                field_schemas={},
                alignment=0,
                anonymous=True,
            )

            parent_field_schema = context["parent_field_schema"]
            parent_field_schema["schema"] = c_schema

            for i, item_schema in enumerate(py_schema["items_schema"]):
                c_f_schema = CStructFieldSchema(
                    type="struct-field",
                    # Will get filled in by the nested visit when we visit the field's schema
                    schema=None,  # pyright: ignore[reportArgumentType]
                    variable_length=(i == variadic_item_index),
                )
                c_schema["field_schemas"][str(i)] = c_f_schema
                _visit(item_schema, {"parent_field_schema": c_f_schema})

            c_schema["alignment"] = _calc_struct_alignment(c_schema["field_schemas"].values())
        case "int":
            c_schema = _simple_c_format_schema(py_schema, "i")
            context["parent_field_schema"]["schema"] = c_schema
        case "float":
            c_schema = _simple_c_format_schema(py_schema, "f")
            context["parent_field_schema"]["schema"] = c_schema
        case "bool":
            c_schema = _simple_c_format_schema(py_schema, "?")
            context["parent_field_schema"]["schema"] = c_schema
        case "bytes":
            c_schema = _simple_c_format_schema(py_schema, "s")
            context["parent_field_schema"]["schema"] = c_schema
        case "uuid":
            # Pydantic will cast this to a UUID object during validation.
            c_schema = _simple_c_format_schema(py_schema, "16s")
            context["parent_field_schema"]["schema"] = c_schema
        # pass on allowed schema types
        case _:
            metadata = get_pydantic_schema_metadata(py_schema)
            if format_schema := metadata.get("format_schema"):
                context["parent_field_schema"]["schema"] = format_schema
            elif format_string := metadata.get("format_string"):
                c_schema = CFormatSchema(
                    type="format",
                    format=format_string,
                    alignment=_calc_fmt_alignment(format_string),
                    validate=_identity,
                    dump=_identity,
                )


def _simple_c_format_schema(py_schema: cs.CoreSchema, default_fmt: str) -> CFormatSchema:
    """Return a simple CFormatSchema for a primitive type.

    Uses the C format string specified in the Pydantic schema's metadata if it exists, otherwise
    uses the provided default.
    """
    fmt = get_pydantic_schema_metadata(py_schema).get("format_string") or default_fmt
    return CFormatSchema(
        type="format",
        format=fmt,
        alignment=_calc_fmt_alignment(fmt),
        validate=operator.itemgetter(0),
        dump=lambda x: (x,),
    )


def _calc_fmt_alignment(fmt: str) -> int:
    """Calculate the alignment of a C format string."""
    return max((calcsize(f) for f in fmt if f.isalpha()), default=0)


def _calc_struct_alignment(field_schemas: Collection[CStructFieldSchema]) -> int:
    """Calculate the alignment of a struct as the max alignment of its fields."""
    return max((f["schema"]["alignment"] for f in field_schemas), default=0)


class PydanticSchemaMetadata(TypedDict, total=False):
    format_string: str
    format_schema: CFormatSchema[Any]


def get_pydantic_schema_metadata(schema: cs.CoreSchema) -> PydanticSchemaMetadata:
    """Get the CModel metadata from a Pydantic core schema, if it exists."""
    return schema.get("metadata", {}).get(SCHEMA_METADATA_KEY, {})


def _identity(x: Any) -> Any:
    return x


SCHEMA_METADATA_KEY = "cmodel"
