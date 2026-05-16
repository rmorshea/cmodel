from collections.abc import Callable
from collections.abc import Hashable
from collections.abc import Mapping
from io import BytesIO
from operator import itemgetter
from struct import Struct
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import NotRequired
from typing import TypedDict
from typing import get_args
from uuid import UUID

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema as cs

import cmodel
from cmodel import _utils

if TYPE_CHECKING:
    from cmodel.base import CModel

CORE_SCHEMA_TYPES = get_args(cs.CoreSchemaType)


type EndianType = Literal["native", "little", "big", "network"]
"""The endianness of a C format."""
type SizeType = Literal["standard", "native"]
"""Whether to use standard sizes for C types or native sizes."""


type Prefix = Literal["@", "=", "<", ">", "!"]
"""A type for valid struct format string prefixes."""
PREFIXES = set(get_args(Prefix))
"""A set of valid struct format string prefixes."""


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


class CPackContext(TypedDict):
    """Context passed to CEncoderSchema pack functions."""

    struct_schema: "CStructSchema"
    """The schema of the struct currently being packed."""
    field_name: str
    """The name of the field being packed."""


class CUnpackContext(TypedDict):
    """Context passed to CEncoderSchema unpack functions."""

    struct_schema: "CStructSchema"
    """The schema of the struct currently being packed."""
    field_name: str
    """The name of the field being unpacked."""


class CSchemaBuildContext(TypedDict):
    """Context passed to functions that build C schemas."""

    endian_type: EndianType
    """The endianness of the current struct being encoded."""
    size_type: SizeType
    """Whether the current struct being encoded uses standard sizes for C types or native sizes."""


class CEncoderSchema[T](TypedDict):
    """An object that can pack and unpack a value to and from a binary buffer."""

    type: Literal["encoder"]

    size: int | None
    """The size of this value in bytes - None if variable length."""
    alignment: int
    """The alignment requirement of this value in bytes."""
    unpack: Callable[[BytesIO, CUnpackContext], T]
    """A function to read this value from a binary buffer."""
    pack: Callable[[BytesIO, T, CPackContext], Any]
    """A function to write this value to a binary buffer."""
    schema_equality_info: Hashable
    """A value used to determine if two CEncoderSchemas are equal."""


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
    tag_schema: CEncoderSchema
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
    size_type: SizeType
    """Whether to use standard sizes for C types or native sizes."""
    endian_type: EndianType
    """The endianness of this struct, which determines the format prefix for its fields."""
    anonymous: bool
    """Anonymous structs become tuples instead of dicts when unpacked."""
    cls: NotRequired["type[CModel]"]
    """The CModel class that this schema corresponds to."""


type CSchema = CStructSchema | CEncoderSchema | CTaggedUnionSchema
"""Any C schema"""


def unpack_c_schema(io: BytesIO, schema: CSchema) -> Any:
    """Unpack a C struct from a buffer according to the provided schema."""
    return _unpack_c_schema(
        io,
        schema,
        {
            "field_name": "",
            "struct_schema": _placeholder_struct_schema(anonymous=True),
        },
    )


def _unpack_c_schema(io: BytesIO, schema: CSchema, context: CUnpackContext) -> Any:
    """Unpack a C struct from a buffer according to the provided schema."""
    match schema["type"]:
        case "encoder":
            return schema["unpack"](io, context)
        case "struct":
            alignment = schema["alignment"]
            field_schemas = schema["field_schemas"]
            if schema["anonymous"]:
                tuple_values: list[Any] = []
                field_list = tuple(field_schemas.values())
                # anonymous struct can't refer to preceding fields by name
                context = {"struct_schema": schema, "field_name": ""}
                for idx, s in enumerate(field_list):
                    tuple_values.append(_unpack_c_schema(io, s["schema"], context))
                    io.seek(_next_padding(io.tell(), idx, field_list, alignment), 1)
                return tuple(tuple_values)
            else:
                dict_values: dict[str, Any] = {}
                context = {
                    "struct_schema": schema,
                    "field_name": "",  # placeholder, will be set correctly in loop
                }
                field_list = tuple(field_schemas.values())
                for idx, (f, s) in enumerate(field_schemas.items()):
                    dict_values[f] = _unpack_c_schema(
                        io,
                        s["schema"],
                        {**context, "field_name": f},
                    )
                    io.seek(_next_padding(io.tell(), idx, field_list, alignment), 1)
                return dict_values
        case "tagged-union":
            tag_schema = schema["tag_schema"]
            tag_size = tag_schema["size"]
            if tag_size is None:
                msg = "Tag schema for tagged union must have a fixed size"
                raise ValueError(msg)
            tag_value = _unpack_c_schema(io, tag_schema, context)
            io.seek(io.tell() - tag_size, 0)  # rewind to the start of the tag field
            variant_schema = schema["variant_schemas"].get(tag_value)
            if variant_schema is None:
                msg = f"Invalid tag value {tag_value} for tagged union"
                raise ValueError(msg)
            return _unpack_c_schema(io, variant_schema, context)
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def pack_c_schema(io: BytesIO, schema: CSchema, value: Any) -> None:
    """Pack a value into a buffer according to the provided C schema."""
    return _pack_c_schema(
        io,
        schema,
        value,
        {
            "field_name": "",
            "struct_schema": _placeholder_struct_schema(anonymous=True),
        },
    )


def _pack_c_schema(io: BytesIO, schema: CSchema, value: Any, context: CPackContext) -> None:
    match schema["type"]:
        case "encoder":
            schema["pack"](io, value, context)
        case "struct":
            alignment = schema["alignment"]
            field_schemas = schema["field_schemas"]
            if schema["anonymous"]:
                field_list = tuple(field_schemas.values())
                for idx, (s, v) in enumerate(zip(field_list, value, strict=True)):
                    _pack_c_schema(io, s["schema"], v, {"struct_schema": schema, "field_name": ""})
                    io.write(b"\x00" * _next_padding(io.tell(), idx, field_list, alignment))
            else:
                field_list = tuple(field_schemas.values())
                for idx, (f, s) in enumerate(field_schemas.items()):
                    _pack_c_schema(
                        io,
                        s["schema"],
                        value[f],
                        {"struct_schema": schema, "field_name": f},
                    )
                    io.write(b"\x00" * _next_padding(io.tell(), idx, field_list, alignment))
        case "tagged-union":
            tag_value = value[schema["tag_field"]]
            variant_schema = schema["variant_schemas"].get(tag_value)
            if variant_schema is None:
                msg = f"Invalid tag value {tag_value} for tagged union"
                raise ValueError(msg)
            _pack_c_schema(io, variant_schema, value, context)
        case _:
            msg = f"Unsupported schema type: {schema['type']}"
            raise TypeError(msg)


def c_schema_from_pydantic_core_schema(
    py_schema: cs.CoreSchema,
    handler: GetCoreSchemaHandler,
) -> CSchema:
    """Convert a Pydantic core schema to a CModel schema."""
    struct_schema = _placeholder_struct_schema()
    field_schema = _placeholder_struct_field_schema()
    _visit(
        py_schema,
        {
            "struct_schema": struct_schema,
            "field_schema": field_schema,
            "pydantic_handler": handler,
        },
    )
    return field_schema["schema"]


class _VisitorContext(TypedDict):
    """Context for the schema visitor."""

    struct_schema: CStructSchema
    """The schema of the struct currently being visited."""
    field_schema: CStructFieldSchema
    """The schema of the current field being visited."""
    pydantic_handler: GetCoreSchemaHandler
    """The handler to resolve references to other schemas."""


def _visit(
    py_schema: cs.CoreSchema,
    context: _VisitorContext,
) -> None:
    """Visitor function to convert a Pydantic core schema to a CModel schema."""
    if metadata := _utils.get_pydantic_schema_metadata(py_schema):
        c_schema = _encoder_schema_from_pydantic_metadata(metadata, context)
        context["field_schema"]["schema"] = c_schema
        if c_schema["size"] is None:
            context["field_schema"]["variable_length"] = True
        return
    match py_schema["type"]:
        case "model":
            _visit_model(py_schema, context)
        case "model-fields":
            _visit_model_fields(py_schema, context)
        case "tuple":
            _visit_tuple(py_schema, context)
        case "tagged-union":
            _visit_tagged_union(py_schema, context)
        case "default":
            _visit(py_schema["schema"], context)
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
            c_schema = _make_uuid_schema(context)
            context["field_schema"]["schema"] = c_schema
        case "definition-ref":
            # TODO: use a similar ref schema mechanism that Pydantic does - if we've seen the
            # reference ID we should be able to reuse the same CSchema object.
            py_schema = context["pydantic_handler"].resolve_ref_schema(py_schema)
            _visit(py_schema, context)
        # pass on allowed schema types
        case _:
            msg = f"Unsupported schema type: {py_schema['type']}"
            raise TypeError(msg)


def _visit_model(
    py_schema: cs.ModelSchema,
    context: _VisitorContext,
) -> None:
    if not issubclass(cls := py_schema["cls"], cmodel.CModel):
        msg = f"Only CModel subclasses can be used as fields in a CModel, got {cls}"
        raise TypeError(msg)

    c_schema = CStructSchema(
        type="struct",
        field_schemas={},
        alignment=cls.c_alignment,
        endian_type=cls.c_endian_type,
        size_type=cls.c_size_type,
        cls=cls,
        anonymous=False,
    )

    field_schema = context["field_schema"]
    field_schema["schema"] = c_schema

    _visit(
        py_schema["schema"],
        {
            "struct_schema": c_schema,
            "field_schema": _placeholder_struct_field_schema(),
            "pydantic_handler": context["pydantic_handler"],
        },
    )

    c_field_schemas = c_schema["field_schemas"].values()
    c_schema["alignment"] = cls.c_alignment or _utils.get_field_schema_alignment(c_field_schemas)

    _check_c_struct_schema(field_schema, c_schema)


def _visit_model_fields(
    py_schema: cs.ModelFieldsSchema,
    context: _VisitorContext,
) -> None:
    struct_schema = context["struct_schema"]
    for f_name, py_f_schema in py_schema["fields"].items():
        c_f_schema = _placeholder_struct_field_schema(
            variable_length=py_f_schema.get("extra", {}).get("c_variable_length", False)
        )
        struct_schema["field_schemas"][f_name] = c_f_schema
        _visit(py_f_schema["schema"], {**context, "field_schema": c_f_schema})


def _visit_tuple(py_schema: cs.TupleSchema, context: _VisitorContext) -> None:
    py_items_schema = py_schema["items_schema"]
    variadic_item_index = py_schema.get("variadic_item_index", -1)
    if variadic_item_index >= 0 and variadic_item_index + 1 != len(py_items_schema):
        msg = "CModel does not support variadic tuples"
        raise ValueError(msg)

    # Tuples are treated as anonymous structs
    c_schema = CStructSchema(
        type="struct",
        field_schemas={},
        alignment=0,  # placeholder
        size_type=context["struct_schema"]["size_type"],
        endian_type=context["struct_schema"]["endian_type"],
        anonymous=True,
    )

    field_schema = context["field_schema"]
    field_schema["schema"] = c_schema

    for i, item_schema in enumerate(py_schema["items_schema"]):
        c_f_schema = _placeholder_struct_field_schema(variable_length=i == variadic_item_index)
        c_schema["field_schemas"][str(i)] = c_f_schema
        _visit(item_schema, {**context, "field_schema": c_f_schema})

    c_schema["alignment"] = _utils.get_field_schema_alignment(c_schema["field_schemas"].values())

    _check_c_struct_schema(field_schema, c_schema)


def _visit_tagged_union(py_schema: cs.TaggedUnionSchema, context: _VisitorContext) -> None:
    if not isinstance(tag_field := py_schema["discriminator"], str):
        msg = f"Only string discriminators are supported for tagged unions, got {tag_field}"
        raise TypeError(msg)

    # A slightly hacky way to get the schema for each choice by capturing them in a fake field.
    c_choice_fields: Mapping[Hashable, CStructFieldSchema] = {}
    for py_choice_value, py_choice_schema in py_schema["choices"].items():
        fake_field = _placeholder_struct_field_schema()  # captures the choice schema
        _visit(py_choice_schema, {**context, "field_schema": fake_field})
        c_choice_fields[py_choice_value] = fake_field
    if not c_choice_fields:
        msg = "Tagged unions must have at least one variant"
        raise ValueError(msg)

    # The above mechanism allows us to check whether the choices are variable length or not.
    variable_length_values = [c["variable_length"] for c in c_choice_fields.values()]
    if any(variable_length_values):
        context["field_schema"]["variable_length"] = True

    # Now we can build the tagged union schema using the captured choice schemas.
    c_choices = {k: v["schema"] for k, v in c_choice_fields.items()}

    tag_schemas: list[CEncoderSchema] = []
    for c_schema in c_choices.values():
        match c_schema["type"]:
            case "struct":
                if c_schema["anonymous"]:
                    # This is because we need to know the name of the tag field to find.
                    msg = f"Tagged union variants cannot be anonymous structs, got {c_schema}"
                    raise ValueError(msg)
                maybe_tag_schema = c_schema["field_schemas"][tag_field]["schema"]
                if maybe_tag_schema["type"] != "encoder":
                    msg = (
                        f"Tag field {tag_field} in tagged union variants "
                        f"must be CEncoded, got {maybe_tag_schema}"
                    )
                    raise TypeError(msg)
                tag_schemas.append(maybe_tag_schema)

    if not tag_schemas:
        msg = f"Tagged union variants must include discriminator field {tag_field}"
        raise ValueError(msg)

    tag_schema = tag_schemas[0]
    tag_schema_equality_infos = {tag_schema["schema_equality_info"] for tag_schema in tag_schemas}
    if len(tag_schema_equality_infos) != 1:
        msg = f"All variants of a tagged union must have the same tag schema, got {tag_schemas}"
        raise ValueError(msg)

    context["field_schema"]["schema"] = CTaggedUnionSchema(
        type="tagged-union",
        alignment=max(c_schema["alignment"] for c_schema in c_choices.values()),
        tag_field=tag_field,
        tag_schema=tag_schema,
        variant_schemas=c_choices,
    )


def _make_uuid_schema(context: _VisitorContext) -> CEncoderSchema:
    return _encoder_schema_from_c_format(
        cmodel.CFormat(
            format="16s",
            validate=lambda x: UUID(bytes=x[0]),
            dump=lambda x: (x.bytes,),
        ),
        context,
    )


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


def _simple_format_schema(fmt: str, context: _VisitorContext) -> CEncoderSchema:
    """Return a CEncoderSchema for a simple scalar type represented as a struct format string."""
    return _encoder_schema_from_c_format(
        cmodel.CFormat(
            format=fmt,
            validate=itemgetter(0),
            dump=lambda x: (x,),
        ),
        context,
    )


def _encoder_schema_from_pydantic_metadata(
    metadata: _utils.PydanticSchemaMetadata, context: _VisitorContext
) -> CEncoderSchema:
    """Convert a CFormatSchema from the metadata on a Pydantic core schema."""
    match metadata:
        case {"c_encoded": c_encoded}:
            struct_schema = context["struct_schema"]
            return c_encoded.get_encoder({
                "endian_type": struct_schema["endian_type"],
                "size_type": struct_schema["size_type"],
            })
        case {"c_format": c_format}:
            return _encoder_schema_from_c_format(c_format, context)
        case _:
            msg = f"Unsupported CModel metadata: {metadata}"
            raise TypeError(msg)


def _encoder_schema_from_c_format(
    c_format: "cmodel.CFormat",
    context: _VisitorContext,
) -> CEncoderSchema:
    """Convert a CFormat to a CEncoderSchema using the provided endianness and size type."""
    struct_schema = context["struct_schema"]
    prefix = get_c_format_prefix(
        struct_schema["endian_type"],
        struct_schema["size_type"],
        error_msg=f" for {cls}" if (cls := struct_schema.get("cls")) else "",
    )

    compiled_fmt = Struct(prefix + c_format.format)
    # create aliases to avoid attribute access cost in pack/unpack functions
    fmt_pack = compiled_fmt.pack
    fmt_unpack = compiled_fmt.unpack
    fmt_size = compiled_fmt.size

    return CEncoderSchema(
        type="encoder",
        size=fmt_size,
        alignment=_utils.get_format_alignment(prefix, c_format.format),
        unpack=lambda io, _: c_format.validate(fmt_unpack(io.read(fmt_size))),
        pack=lambda io, value, _: io.write(fmt_pack(*c_format.dump(value))),
        schema_equality_info=(prefix, c_format.format),
    )


def _placeholder_struct_schema(
    *,
    anonymous: bool = False,
    endian_type: EndianType = "native",
    size_type: SizeType = "native",
) -> CStructSchema:
    """Return a placeholder CStructSchema that can be used to build up a CStructSchema."""
    return CStructSchema(
        type="struct",
        field_schemas={},
        alignment=0,  # placeholder
        endian_type=endian_type,
        size_type=size_type,
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


def _next_padding(
    position: int,
    idx: int,
    field_schemas: tuple[CStructFieldSchema, ...],
    struct_align: int,
) -> int:
    """Return the number of padding bytes needed after field *idx*.

    Between fields, padding aligns to the next field's natural alignment capped
    by *struct_align* (pack(n) semantics).  After the last field, trailing
    padding aligns to the struct alignment.

    Args:
        position: the current byte position in the struct
        idx: the index of the current field
        field_schemas: the schemas of all fields in the struct, in order
        struct_align: the overall struct alignment to cap field alignments at
    """
    next_align = (
        min(field_schemas[idx + 1]["schema"]["alignment"], struct_align)
        if idx + 1 < len(field_schemas)
        else struct_align
    )
    return (next_align - (position % next_align)) % next_align
