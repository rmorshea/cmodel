import operator
from collections.abc import Callable
from collections.abc import Mapping
from io import BytesIO
from struct import Struct
from typing import Any
from typing import Literal
from typing import TypedDict
from typing import get_args
from uuid import UUID

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema as cs

import cmodel
from cmodel import _utils

CORE_SCHEMA_TYPES = get_args(cs.CoreSchemaType)


Endian = Literal[
    # @ is excluded because it means "native" endianness but also native alignment
    "=",  # native
    "<",  # little-endian
    ">",  # big-endian
    "!",  # network (big-endian)
]
"""The endianness (or byte order) of a C struct.

This only affects byte order. Alignment is determined separately by the alignment
of the fields and any user-specified alignment on a model.
"""

type CFormatByEndian = Mapping[Endian, Struct]
"""A mapping of endianness to `struct.Struct` objects for a particular format string."""


class CFormatSchema[T](TypedDict):
    """A schema for a single field in a C struct."""

    type: Literal["format"]

    format: CFormatByEndian
    """A mapping of endianness to `struct.Struct` objects for this format string."""
    alignment: int
    """The alignment of this schema in bytes."""
    validate: Callable[[tuple[Any, ...]], T]
    """A function to convert the raw tuple produced by `struct.unpack` into a Python value."""
    dump: Callable[[T], tuple[Any, ...]]
    """A function to convert a Python value into a tuple that can be passed to `struct.pack`."""


class CStructFieldSchema(TypedDict):
    """A schema for a single field in a C struct."""

    type: Literal["struct-field"]

    schema: "CSchema"
    """The schema for this field, which may be a CFormatSchema for a simple field or a nested"""
    variable_length: bool
    """Whether this field consumes the rest of the buffer when unpacking."""


class CStructSchema(TypedDict):
    """A schema for a C struct."""

    type: Literal["struct"]

    field_schemas: dict[str, CStructFieldSchema]
    """The inner schemas for each field in the struct, keyed by field name."""
    alignment: int
    """The alignment of this struct in bytes computed as the max alignment of its fields."""
    anonymous: bool
    """Anonymous structs become tuples instead of dicts when unpacked."""


CSchema = CStructSchema | CFormatSchema
"""Any C schema"""


def unpack_c_schema(io: BytesIO, schema: CSchema, endian: Endian) -> Any:
    """Unpack a C struct from a buffer according to the provided schema."""
    match schema["type"]:
        case "format":
            fmt = schema["format"][endian]
            raw_value = fmt.unpack_from(io.getbuffer(), io.tell())
            io.seek(fmt.size, 1)
            return schema["validate"](raw_value)
        case "struct":
            alignment = schema["alignment"]
            field_schemas = schema["field_schemas"]
            if schema["anonymous"]:
                tuple_values: list[Any] = []
                for s in field_schemas.values():
                    tuple_values.append(unpack_c_schema(io, s["schema"], endian))
                    # add padding to align to the next field
                    io.seek((alignment - (io.tell() % alignment)) % alignment, 1)
                return tuple(tuple_values)
            else:
                dict_values: dict[str, Any] = {}
                for f, s in field_schemas.items():
                    dict_values[f] = unpack_c_schema(io, s["schema"], endian)
                    # add padding to align to the next field
                    io.seek((alignment - (io.tell() % alignment)) % alignment, 1)
                return dict_values
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def pack_c_schema(io: BytesIO, schema: CSchema, endian: Endian, value: Any) -> None:
    """Pack a value into a buffer according to the provided C schema."""
    match schema["type"]:
        case "format":
            args = schema["dump"](value)
            io.write(schema["format"][endian].pack(*args))
        case "struct":
            alignment = schema["alignment"]
            field_schemas = schema["field_schemas"]
            if schema["anonymous"]:
                for s, v in zip(field_schemas.values(), value, strict=True):
                    pack_c_schema(io, s["schema"], endian, v)
                    # add padding to align to the next field
                    io.write(b"\x00" * ((alignment - (io.tell() % alignment)) % alignment))
            else:
                for f, s in field_schemas.items():
                    pack_c_schema(io, s["schema"], endian, value[f])
                    # add padding to align to the next field
                    io.write(b"\x00" * ((alignment - (io.tell() % alignment)) % alignment))
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def c_schema_from_pydantic_core_schema(
    core_schema: cs.CoreSchema,
    handler: GetCoreSchemaHandler,
) -> CSchema:
    """Convert a Pydantic core schema to a CModel schema."""
    fake_field_schema = CStructFieldSchema(
        type="struct-field",
        schema=None,  # pyright: ignore[reportArgumentType]
        variable_length=False,
    )
    _visit(core_schema, handler, {"parent_field_schema": fake_field_schema})
    return fake_field_schema["schema"]


class _VisitorContext(TypedDict):
    """Context for the schema visitor."""

    parent_field_schema: CStructFieldSchema
    """The schema of the current field being visited."""


def _visit(
    py_schema: cs.CoreSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:
    """Visitor function to convert a Pydantic core schema to a CModel schema."""
    metadata = _utils.get_pydantic_schema_metadata(py_schema)
    if format_schema := metadata.get("format_schema"):
        context["parent_field_schema"]["schema"] = format_schema
        return
    match py_schema["type"]:
        case "model":
            _visit_model(py_schema, handler, context)
        case "model-fields":
            _visit_model_fields(py_schema, handler, context)
        case "tuple":
            _visit_tuple(py_schema, handler, context)
        case "int":
            c_schema = _simple_format_schema("i")
            context["parent_field_schema"]["schema"] = c_schema
        case "float":
            c_schema = _simple_format_schema("f")
            context["parent_field_schema"]["schema"] = c_schema
        case "bool":
            c_schema = _simple_format_schema("?")
            context["parent_field_schema"]["schema"] = c_schema
        case "bytes":
            c_schema = _simple_format_schema("s")
            context["parent_field_schema"]["schema"] = c_schema
        case "uuid":
            _visit_uuid(py_schema, handler, context)
        case "definition-ref":
            # TODO: use a similar ref schema mechanism that Pydantic does - if we've seen the
            # reference ID we should be able to reuse the same CSchema object.
            py_schema = handler.resolve_ref_schema(py_schema)
            _visit(py_schema, handler, context)
        # pass on allowed schema types
        case _:
            msg = f"Unsupported schema type: {py_schema['type']}"
            raise TypeError(msg)


def _visit_model(
    py_schema: cs.ModelSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:

    c_schema = CStructSchema(
        type="struct",
        field_schemas={},
        alignment=0,  # placeholder
        anonymous=False,
    )

    parent_field_schema = context["parent_field_schema"]
    parent_field_schema["schema"] = c_schema

    _visit(py_schema["schema"], handler, context)

    # Use the model defined alignment or calculate it based on alignment requirement of fields
    if issubclass(cls := py_schema["cls"], cmodel.CModel) and cls.c_alignment is not None:
        alignment = cls.c_alignment
    else:
        alignment = _utils.get_field_schema_alignment(c_schema["field_schemas"].values())

    c_schema["alignment"] = alignment

    _check_c_struct_schema(parent_field_schema, c_schema)


def _visit_model_fields(
    py_schema: cs.ModelFieldsSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:
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
        _visit(py_f_schema["schema"], handler, {"parent_field_schema": c_f_schema})


def _visit_tuple(
    py_schema: cs.TupleSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:
    py_items_schema = py_schema["items_schema"]
    variadic_item_index = py_schema.get("variadic_item_index", -1)
    if variadic_item_index > 0 and variadic_item_index + 1 != len(py_items_schema):
        msg = "CModel does not support variadic tuples"
        raise ValueError(msg)

    # Tuples are treated as anonymous structs
    c_schema = CStructSchema(
        type="struct",
        field_schemas={},
        alignment=0,  # placeholder
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
        _visit(item_schema, handler, {"parent_field_schema": c_f_schema})

    c_schema["alignment"] = _utils.get_field_schema_alignment(c_schema["field_schemas"].values())

    _check_c_struct_schema(parent_field_schema, c_schema)


def _visit_uuid(
    py_schema: cs.UuidSchema,  # noqa: ARG001
    handler: GetCoreSchemaHandler,  # noqa: ARG001
    context: _VisitorContext,
) -> None:
    c_schema = CFormatSchema(
        type="format",
        format=_utils.compile_format_by_endian("16s"),
        alignment=_utils.get_format_alignment("s"),
        validate=lambda x: UUID(bytes=x[0]),
        dump=lambda x: (x.bytes,),
    )
    context["parent_field_schema"]["schema"] = c_schema


def _check_c_struct_schema(
    parent_field_schema: CStructFieldSchema,
    c_schema: CStructSchema,
) -> None:
    for f_index, f_schema in enumerate(c_schema["field_schemas"].values()):
        if f_schema["variable_length"]:
            if f_index != len(c_schema["field_schemas"]) - 1:
                msg = "Variable length fields must be the last field in a struct"
                raise ValueError(msg)
            parent_field_schema["variable_length"] = True


def _simple_format_schema(fmt: str) -> CFormatSchema:
    """Return a CFormatSchema from a format string without special validate or dump functions."""
    return CFormatSchema(
        type="format",
        format=_utils.compile_format_by_endian(fmt),
        alignment=_utils.get_format_alignment(fmt),
        validate=operator.itemgetter(0),
        dump=lambda x: (x,),
    )
