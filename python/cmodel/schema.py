import operator
from collections.abc import Callable
from collections.abc import Hashable
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


type EndianType = Literal["native", "little", "big", "network"]
"""The endianness of a C format."""
type SizeType = Literal["standard", "native"]
"""Whether to use standard sizes for C types or native sizes."""


# We define this as a separate type in case, in the future we want a non-precompiled version
# in the schema (perhaps to be transferable to other languages). This could be defined as a
# union of this and a CFormatString type, for example. For now though, we only have and handle
# the compiled version.
class CFormatCompiled(TypedDict):
    """A compiled C format."""

    compiled: Struct


class CFormatSchema[T](TypedDict):
    """A schema for a single C value."""

    type: Literal["format"]

    format: CFormatCompiled
    """The format for this field compiled for each endian."""
    alignment: int
    """The alignment of this schema in bytes."""
    validate: Callable[[tuple[Any, ...]], T]
    """A function to convert the raw tuple produced by `struct.unpack` into a Python value."""
    dump: Callable[[T], tuple[Any, ...]]
    """A function to convert a Python value into a tuple that can be passed to `struct.pack`."""


class CRawSchema[T](TypedDict):
    """A schema for a C-compatible bytes field."""

    type: Literal["raw"]

    size: int | None
    """The size of the bytes field. None is variable-length."""
    alignment: int
    """The alignment of the bytes field."""
    validate: Callable[[bytes], T]
    """A function to convert raw bytes into a Python value."""
    dump: Callable[[T], bytes]
    """A function to convert a Python value into raw bytes."""


class CStructFieldSchema(TypedDict):
    """A schema for a single field in a C struct."""

    type: Literal["struct-field"]

    schema: "CSchema"
    """The schema for this field, which may be a CFormatSchema for a simple field or a nested"""
    variable_length: bool
    """Whether this field consumes the rest of the buffer when unpacking."""


class CTaggedUnionSchema(TypedDict):
    """A schema for a tagged union in a C struct."""

    type: Literal["tagged-union"]

    alignment: int
    """The alignment of this union in bytes computed as the max alignment of its variants."""
    tag_field: str
    """The name of the field that serves as the tag for this union."""
    tag_schema: CFormatSchema
    """The schema for the tag field that determines which variant of the union is active."""
    variant_schemas: dict[Any, "CSchema"]
    """A mapping of tag values to the schemas for each variant of the union."""


class CStructSchema(TypedDict):
    """A schema for a C struct."""

    type: Literal["struct"]

    field_schemas: dict[str, CStructFieldSchema]
    """The inner schemas for each field in the struct, keyed by field name."""
    alignment: int
    """The alignment of this struct in bytes computed as the max alignment of its fields."""
    prefix: _utils.Prefix
    """The format prefix to use for this struct, determined by the endianness and size"""
    anonymous: bool
    """Anonymous structs become tuples instead of dicts when unpacked."""


CSchema = CStructSchema | CFormatSchema | CRawSchema | CTaggedUnionSchema
"""Any C schema"""


def unpack_c_schema(io: BytesIO, schema: CSchema) -> Any:
    """Unpack a C struct from a buffer according to the provided schema."""
    match schema["type"]:
        case "raw":
            raw_bytes = io.read() if schema["size"] is None else io.read(schema["size"])
            return schema["validate"](raw_bytes)
        case "format":
            fmt = schema["format"]["compiled"]
            raw_value = fmt.unpack_from(io.getbuffer(), io.tell())
            io.seek(fmt.size, 1)
            return schema["validate"](raw_value)
        case "struct":
            alignment = schema["alignment"]
            field_schemas = schema["field_schemas"]
            if schema["anonymous"]:
                tuple_values: list[Any] = []
                for s in field_schemas.values():
                    tuple_values.append(unpack_c_schema(io, s["schema"]))
                    # add padding to align to the next field
                    io.seek((alignment - (io.tell() % alignment)) % alignment, 1)
                return tuple(tuple_values)
            else:
                dict_values: dict[str, Any] = {}
                for f, s in field_schemas.items():
                    dict_values[f] = unpack_c_schema(io, s["schema"])
                    # add padding to align to the next field
                    io.seek((alignment - (io.tell() % alignment)) % alignment, 1)
                return dict_values
        case "tagged-union":
            tag_schema = schema["tag_schema"]
            tag_size = tag_schema["format"]["compiled"].size
            tag_value = unpack_c_schema(io, tag_schema)
            io.seek(io.tell() - tag_size, 0)  # rewind to the start of the tag field
            variant_schema = schema["variant_schemas"].get(tag_value)
            if variant_schema is None:
                msg = f"Invalid tag value {tag_value} for tagged union"
                raise ValueError(msg)
            return unpack_c_schema(io, variant_schema)
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def pack_c_schema(io: BytesIO, schema: CSchema, value: Any) -> None:
    """Pack a value into a buffer according to the provided C schema."""
    match schema["type"]:
        case "raw":
            raw_bytes = schema["dump"](value)
            if (size := schema["size"]) is not None and len(raw_bytes) != size:
                msg = f"Raw bytes field must be exactly {size} bytes, got {len(raw_bytes)}"
                raise ValueError(msg)
            io.write(raw_bytes)
        case "format":
            args = schema["dump"](value)
            io.write(schema["format"]["compiled"].pack(*args))
        case "struct":
            alignment = schema["alignment"]
            field_schemas = schema["field_schemas"]
            if schema["anonymous"]:
                for s, v in zip(field_schemas.values(), value, strict=True):
                    pack_c_schema(io, s["schema"], v)
                    # add padding to align to the next field
                    io.write(b"\x00" * ((alignment - (io.tell() % alignment)) % alignment))
            else:
                for f, s in field_schemas.items():
                    pack_c_schema(io, s["schema"], value[f])
                    # add padding to align to the next field
                    io.write(b"\x00" * ((alignment - (io.tell() % alignment)) % alignment))
        case "tagged-union":
            tag_value = value[schema["tag_field"]]
            variant_schema = schema["variant_schemas"].get(tag_value)
            if variant_schema is None:
                msg = f"Invalid tag value {tag_value} for tagged union"
                raise ValueError(msg)
            pack_c_schema(io, variant_schema, value)
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def c_schema_from_pydantic_core_schema(
    core_schema: cs.CoreSchema,
    handler: GetCoreSchemaHandler,
) -> CSchema:
    """Convert a Pydantic core schema to a CModel schema."""
    struct_schema = _placeholder_struct_schema()
    field_schema = _placeholder_struct_field_schema()
    _visit(core_schema, handler, {"struct_schema": struct_schema, "field_schema": field_schema})
    return field_schema["schema"]


class _VisitorContext(TypedDict):
    """Context for the schema visitor."""

    struct_schema: CStructSchema
    """The schema of the struct currently being visited."""
    field_schema: CStructFieldSchema
    """The schema of the current field being visited."""


def _visit(
    py_schema: cs.CoreSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:
    """Visitor function to convert a Pydantic core schema to a CModel schema."""
    if metadata := _utils.get_pydantic_metadata(py_schema):
        context["field_schema"]["schema"] = _format_schema_from_pydantic_metadata(context, metadata)
        return
    match py_schema["type"]:
        case "model":
            _visit_model(py_schema, handler, context)
        case "model-fields":
            _visit_model_fields(py_schema, handler, context)
        case "tuple":
            _visit_tuple(py_schema, handler, context)
        case "tagged-union":
            _visit_tagged_union(py_schema, handler, context)
        case "int":
            c_schema = _simple_format_schema("i", context)
            context["field_schema"]["schema"] = c_schema
        case "float":
            c_schema = _simple_format_schema("f", context)
            context["field_schema"]["schema"] = c_schema
        case "bool":
            c_schema = _simple_format_schema("?", context)
            context["field_schema"]["schema"] = c_schema
        case "bytes":
            c_schema = _simple_format_schema("s", context)
            context["field_schema"]["schema"] = c_schema
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
    if not issubclass(cls := py_schema["cls"], cmodel.CModel):
        msg = f"Only CModel subclasses can be used as fields in a CModel, got {cls}"
        raise TypeError(msg)

    c_schema = CStructSchema(
        type="struct",
        field_schemas={},
        alignment=cls.c_alignment,
        prefix=_utils.get_c_format_prefix(cls),
        anonymous=False,
    )

    field_schema = context["field_schema"]
    field_schema["schema"] = c_schema

    _visit(
        py_schema["schema"],
        handler,
        {"struct_schema": c_schema, "field_schema": _placeholder_struct_field_schema()},
    )

    c_field_schemas = c_schema["field_schemas"].values()
    c_schema["alignment"] = cls.c_alignment or _utils.get_field_schema_alignment(c_field_schemas)

    _check_c_struct_schema(field_schema, c_schema)


def _visit_model_fields(
    py_schema: cs.ModelFieldsSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:
    struct_schema = context["struct_schema"]
    for f_name, py_f_schema in py_schema["fields"].items():
        c_f_schema = _placeholder_struct_field_schema(
            variable_length=py_f_schema.get("extra", {}).get("c_variable_length", False)
        )
        struct_schema["field_schemas"][f_name] = c_f_schema
        _visit(
            py_f_schema["schema"],
            handler,
            {**context, "field_schema": c_f_schema},
        )


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
        prefix=context["struct_schema"]["prefix"],
        anonymous=True,
    )

    field_schema = context["field_schema"]
    field_schema["schema"] = c_schema

    for i, item_schema in enumerate(py_schema["items_schema"]):
        c_f_schema = _placeholder_struct_field_schema(variable_length=i == variadic_item_index)
        c_schema["field_schemas"][str(i)] = c_f_schema
        _visit(
            item_schema,
            handler,
            {**context, "field_schema": c_f_schema},
        )

    c_schema["alignment"] = _utils.get_field_schema_alignment(c_schema["field_schemas"].values())

    _check_c_struct_schema(field_schema, c_schema)


def _visit_tagged_union(
    py_schema: cs.TaggedUnionSchema,
    handler: GetCoreSchemaHandler,
    context: _VisitorContext,
) -> None:
    if not isinstance(tag_field := py_schema["discriminator"], str):
        msg = f"Only string discriminators are supported for tagged unions, got {tag_field}"
        raise TypeError(msg)

    # A slightly hacky way to get the schema for each choice by capturing them in a fake field.
    c_choice_fields: Mapping[Hashable, CStructFieldSchema] = {}
    for py_choice_value, py_choice_schema in py_schema["choices"].items():
        fake_field = _placeholder_struct_field_schema()  # captures the choice schema
        _visit(py_choice_schema, handler, {**context, "field_schema": fake_field})
        c_choice_fields[py_choice_value] = fake_field
    if not c_choice_fields:
        msg = "Tagged unions must have at least one variant"
        raise ValueError(msg)

    # The above mechanism does allow us to check whether the choices are variable length or not.
    variable_length_values = [c["variable_length"] for c in c_choice_fields.values()]
    if any(variable_length_values):
        if all(variable_length_values):
            context["field_schema"]["variable_length"] = True
        else:
            msg = "All variants of a tagged union must be variable length if any of them are"
            raise ValueError(msg)

    # Now we can build the tagged union schema using the captured choice schemas.
    c_choices = {k: v["schema"] for k, v in c_choice_fields.items()}

    tag_schemas: list[CSchema] = []
    for c_schema in c_choices.values():
        match c_schema["type"]:
            case "struct":
                if c_schema["anonymous"]:
                    msg = f"Tagged union variants cannot be anonymous structs, got {c_schema}"
                    raise ValueError(msg)
                tag_schemas.append(c_schema["field_schemas"][tag_field]["schema"])

    if not tag_schemas:
        msg = f"Tagged union variants must include discriminator field {tag_field}"
        raise ValueError(msg)

    tag_schema = tag_schemas[0]
    if tag_schema["type"] != "format":
        msg = f"Tag field {tag_field} must be a simple format field, got {tag_schema['type']}"
        raise TypeError(msg)

    for next_t_schema in tag_schemas[1:]:
        if not _format_schemas_equal(tag_schema, next_t_schema):
            msg = (
                f"All variants of a tagged union must have the same tag field schema, "
                f"got {tag_schema} and {next_t_schema}"
            )
            raise ValueError(msg)

    context["field_schema"]["schema"] = CTaggedUnionSchema(
        type="tagged-union",
        alignment=max(c_schema["alignment"] for c_schema in c_choices.values()),
        tag_field=tag_field,
        tag_schema=tag_schema,
        variant_schemas=c_choices,
    )


def _visit_uuid(
    py_schema: cs.UuidSchema,  # noqa: ARG001
    handler: GetCoreSchemaHandler,  # noqa: ARG001
    context: _VisitorContext,
) -> None:
    compiled = Struct(context["struct_schema"]["prefix"] + "16s")
    c_schema = CFormatSchema(
        type="format",
        format={"compiled": compiled},
        alignment=_utils.get_format_alignment(context["struct_schema"]["prefix"], "s"),
        validate=lambda x: UUID(bytes=x[0]),
        dump=lambda x: (x.bytes,),
    )
    context["field_schema"]["schema"] = c_schema


def _check_c_struct_schema(
    field_schema: CStructFieldSchema,
    c_schema: CStructSchema,
) -> None:
    for f_index, f_schema in enumerate(c_schema["field_schemas"].values()):
        if f_schema["variable_length"]:
            if f_index != len(c_schema["field_schemas"]) - 1:
                msg = "Variable length fields must be the last field in a struct"
                raise ValueError(msg)
            field_schema["variable_length"] = True


def _simple_format_schema(fmt: str, context: _VisitorContext) -> CFormatSchema:
    """Return a CFormatSchema from a format string without special validate or dump functions."""
    compiled = Struct(context["struct_schema"]["prefix"] + fmt)
    return CFormatSchema(
        type="format",
        format={"compiled": compiled},
        alignment=_utils.get_format_alignment(context["struct_schema"]["prefix"], fmt),
        validate=operator.itemgetter(0),
        dump=lambda x: (x,),
    )


def _format_schemas_equal(left: CFormatSchema, right: CSchema) -> bool:
    return (
        right["type"] == "format"
        and left["format"]["compiled"].format == right["format"]["compiled"].format
        and left["alignment"] == right["alignment"]
    )


def _format_schema_from_pydantic_metadata(
    context: _VisitorContext, metadata: _utils.PydanticMetadata
) -> CFormatSchema | CRawSchema:
    """Convert a CFormatSchema from the metadata on a Pydantic core schema."""
    match metadata:
        case {"c_format": c_format_metadata}:
            fmt = c_format_metadata["format"]
            return CFormatSchema(
                type="format",
                format={"compiled": Struct(context["struct_schema"]["prefix"] + fmt)},
                alignment=_utils.get_format_alignment(context["struct_schema"]["prefix"], fmt),
                validate=c_format_metadata["validate"],
                dump=c_format_metadata["dump"],
            )
        case {"c_raw": c_raw_metadata}:
            schema = CRawSchema(
                type="raw",
                size=c_raw_metadata["size"],
                alignment=c_raw_metadata["alignment"],
                validate=c_raw_metadata["validate"],
                dump=c_raw_metadata["dump"],
            )
            context["field_schema"]["variable_length"] = c_raw_metadata["size"] is None
            return schema
        case _:
            msg = f"Invalid pydantic metadata: {metadata}"
            raise ValueError(msg)


def _placeholder_struct_schema(
    *,
    anonymous: bool = False,
    prefix: _utils.Prefix = "@",
) -> CStructSchema:
    """Return a placeholder CStructSchema that can be used to build up a CStructSchema."""
    return CStructSchema(
        type="struct",
        field_schemas={},
        alignment=0,  # placeholder
        prefix=prefix,
        anonymous=anonymous,
    )


def _placeholder_struct_field_schema(*, variable_length: bool = False) -> CStructFieldSchema:
    """Return a placeholder CStructFieldSchema that can be used to build up a CStructSchema."""
    return CStructFieldSchema(
        type="struct-field",
        # The schema needs to be filled in later by a visitor
        schema=None,  # pyright: ignore[reportArgumentType]
        variable_length=variable_length,
    )
