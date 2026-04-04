import operator
from collections.abc import Callable
from io import BytesIO
from struct import calcsize
from struct import pack
from struct import unpack_from
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


class CFormatSchema[T](TypedDict):
    """A schema for a single field in a C struct."""

    type: Literal["format"]
    format: str
    alignment: int
    size: int
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


class PydanticSchemaMetadata(TypedDict, total=False):
    """Metadata for a Pydantic schema to control how it is converted to a CModel schema."""

    format_schema: CFormatSchema[Any]


def get_pydantic_schema_metadata(schema: cs.CoreSchema) -> PydanticSchemaMetadata:
    """Get the CModel metadata from a Pydantic core schema, if it exists."""
    return schema.get("metadata", {}).get(PYDANTIC_SCHEMA_METADATA_KEY, {})


PYDANTIC_SCHEMA_METADATA_KEY = "cmodel"


def unpack_c_schema(io: BytesIO, schema: CSchema) -> Any:
    """Unpack a C struct from a buffer according to the provided schema."""
    return _unpack(io, schema, 1)


def _unpack(io: BytesIO, schema: CSchema, struct_alignment: int) -> Any:
    match schema["type"]:
        case "format":
            # Seek to the next offset that matches the struct's alignment
            if struct_alignment > 1:
                current_pos = io.tell()
                padding = (struct_alignment - (current_pos % struct_alignment)) % struct_alignment
                io.seek(padding, 1)
            raw_value = unpack_from(schema["format"], io.getbuffer(), io.tell())
            io.seek(schema["size"], 1)
            return schema["validate"](raw_value)
        case "struct":
            values = {}
            new_struct_alignment = schema["alignment"]
            for f_name, f_schema in schema["field_schemas"].items():
                values[f_name] = _unpack(io, f_schema["schema"], new_struct_alignment)
            return tuple(values.values()) if schema["anonymous"] else values
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def pack_c_schema(io: BytesIO, schema: CSchema, value: Any) -> None:
    """Pack a value into a buffer according to the provided C schema."""
    _pack(schema, io, value, 1)


def _pack(schema: CSchema, io: BytesIO, value: Any, struct_alignment: int) -> None:
    match schema["type"]:
        case "format":
            if struct_alignment > 1:
                current_pos = io.tell()
                padding = (struct_alignment - (current_pos % struct_alignment)) % struct_alignment
                io.write(b"\x00" * padding)
            raw_value = schema["dump"](value)
            io.write(pack(schema["format"], *raw_value))
        case "struct":
            new_struct_alignment = schema["alignment"]
            for f_index, (f_name, f_schema) in enumerate(schema["field_schemas"].items()):
                _pack(
                    f_schema["schema"],
                    io,
                    value[f_index] if schema["anonymous"] else value[f_name],
                    new_struct_alignment,
                )
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
    py_schema: cs.CoreSchema, handler: GetCoreSchemaHandler, context: _VisitorContext
) -> None:
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

            _visit(py_schema["schema"], handler, context)

            if issubclass(cls := py_schema["cls"], cmodel.CModel) and cls.c_alignment is not None:
                # Alignment can be specified manually on the model class
                c_schema["alignment"] = cls.c_alignment
            else:
                # Now that we've visited all the fields, we can calculate the struct's alignment as
                # the max alignment of its field alignments.
                c_schema["alignment"] = _utils.calc_struct_alignment(
                    c_schema["field_schemas"].values()
                )
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
                _visit(py_f_schema["schema"], handler, {"parent_field_schema": c_f_schema})
        case "tuple":
            py_items_schema = py_schema["items_schema"]
            variadic_item_index = py_schema.get("variadic_item_index", -1)
            if variadic_item_index > 0 and variadic_item_index + 1 != len(py_items_schema):
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
                _visit(item_schema, handler, {"parent_field_schema": c_f_schema})

            c_schema["alignment"] = _utils.calc_struct_alignment(c_schema["field_schemas"].values())
        case "int":
            c_schema = _maybe_default_format_schema(py_schema, "i")
            context["parent_field_schema"]["schema"] = c_schema
        case "float":
            c_schema = _maybe_default_format_schema(py_schema, "f")
            context["parent_field_schema"]["schema"] = c_schema
        case "bool":
            c_schema = _maybe_default_format_schema(py_schema, "?")
            context["parent_field_schema"]["schema"] = c_schema
        case "bytes":
            c_schema = _maybe_default_format_schema(py_schema, "s")
            context["parent_field_schema"]["schema"] = c_schema
        case "uuid":
            # Pydantic will cast this to a UUID object during validation.
            c_schema = _maybe_default_format_schema(
                py_schema,
                CFormatSchema(
                    type="format",
                    format="16s",
                    alignment=_utils.calc_format_alignment("s"),
                    validate=lambda x: UUID(bytes=x[0]),
                    dump=lambda x: (x.bytes,),
                    size=calcsize("16s"),
                ),
            )
            context["parent_field_schema"]["schema"] = c_schema
        case "definition-ref":
            py_schema = handler.resolve_ref_schema(py_schema)
            _visit(py_schema, handler, context)
        # pass on allowed schema types
        case _:
            metadata = get_pydantic_schema_metadata(py_schema)
            if format_schema := metadata.get("format_schema"):
                context["parent_field_schema"]["schema"] = format_schema
            elif format_string := metadata.get("format_string"):
                c_schema = CFormatSchema(
                    type="format",
                    format=format_string,
                    alignment=_utils.calc_format_alignment(format_string),
                    validate=_utils.identity,
                    dump=_utils.identity,
                    size=calcsize(format_string),
                )
            else:
                msg = f"Unsupported schema type: {py_schema['type']}"
                raise TypeError(msg)


def _maybe_default_format_schema(
    py_schema: cs.CoreSchema,
    default: str | CFormatSchema,
) -> CFormatSchema:
    """Return a default CFormatSchema unless one was specified manually."""
    if (c_schema := get_pydantic_schema_metadata(py_schema).get("format_schema")) is not None:
        return c_schema
    if isinstance(default, str):
        return CFormatSchema(
            type="format",
            format=default,
            alignment=_utils.calc_format_alignment(default),
            validate=operator.itemgetter(0),
            dump=lambda x: (x,),
            size=calcsize(default),
        )
    else:
        return default
