from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from struct import calcsize
from struct import pack
from struct import unpack_from
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import Self
from typing import TypedDict
from typing import overload

from pydantic import BaseModel
from pydantic import GetCoreSchemaHandler
from pydantic import ModelWrapValidatorHandler
from pydantic import SerializationInfo
from pydantic import SerializerFunctionWrapHandler
from pydantic import ValidationInfo
from pydantic import model_serializer
from pydantic import model_validator
from pydantic_core import core_schema as cs
from pydantic_walk_core_schema import walk_core_schema


class CModel(BaseModel):
    """Base class for models that can be packed/unpacked to/from C binary data."""

    c_align: ClassVar[int]
    """The alignment of the C struct this model represents.

    If not specified, the alignment will be calculated as the maximum alignment of the fields in
    the model. This attribute is not inherited and  must be specified explicitely on each subclass.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> cs.CoreSchema:
        try:
            CModel  # type:ignore[reportUnusedExpression] # noqa: B018
        except NameError:
            # we're defining the schema for this class - just return it
            return handler(source)
        else:
            # we're defining the schema for a subclass
            adapter = _ModelSchemaAdapter(handler)
            schema = adapter.adapt(handler(source))
            cls.c_align = max(adapter.field_alignments, default=1)
            return schema

    @classmethod
    def c_unpack(cls, buffer: BytesIO) -> Self:
        """Read a C binary data buffer as a packed struct and return an instance of the model."""
        ctx: _Context = {"io": buffer, "align": 0}
        return cls.model_validate(_USE_BUFFER, context={_CONTEXT_KEY: ctx})

    def c_pack(self, buffer: BytesIO) -> None:
        """Write the model instance to a C binary data buffer as a packed struct."""
        ctx: _Context = {"io": buffer, "align": 0}
        self.model_dump(context={_CONTEXT_KEY: ctx})

    @model_validator(mode="wrap")
    @classmethod
    def _validate_model(
        cls,
        value: Any,
        handler: ModelWrapValidatorHandler,
        info: cs.ValidationInfo,
    ) -> Any:
        if value is _USE_BUFFER:
            # Indicate that we're unpacking by ensuring each field is present and gets "validated".
            # The validator for each field will then read from the buffer because of _USE_BUFFER
            value = dict.fromkeys(cls.model_fields, _USE_BUFFER)
            # Update the alignment for fields in this model.
            ctx = _get_context(info, required=True)
            old_align = cls.c_align
            ctx["align"] = cls.c_align
            try:
                return handler(value)
            finally:
                ctx["align"] = old_align
        else:
            return value

    @model_serializer(mode="wrap")
    def _serialize_model(
        self, handler: SerializerFunctionWrapHandler, info: cs.SerializationInfo
    ) -> Any:
        if ctx := _get_context(info):
            # Update the alignment for fields in this model.
            ctx = _get_context(info, required=True)
            old_align = self.c_align
            ctx["align"] = self.c_align
            try:
                return handler(self)
            finally:
                ctx["align"] = old_align
        else:
            return handler(self)


@dataclass
class CFmt[T]:
    """Metadata for a C field, used in the Annotated type of each field in a CModel."""

    fmt: str
    validate: Callable[[tuple[Any, ...]], T] = lambda x: x  # pyright: ignore[reportAssignmentType]
    dump: Callable[[T], tuple[Any, ...]] = lambda x: x  # pyright: ignore[reportAssignmentType]

    def __get_pydantic_core_schema__(
        self,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> cs.CoreSchema:
        fmt = self.fmt
        size = calcsize(fmt)
        validate = self.validate
        dump = self.dump

        def validator(value: Any, info: ValidationInfo) -> Any:
            if value is _USE_BUFFER:
                ctx = _get_context(info, required=True)
                io = ctx["io"]
                align = ctx["align"]
                value = unpack_from(fmt, io.getbuffer(), io.tell())
                io.seek(size + (align - (size % align)) % align, 1)
                return validate(value)
            else:
                return value

        def serializer(value: Any, info: SerializationInfo) -> Any:
            if ctx := _get_context(info):
                io = ctx["io"]
                align = ctx["align"]
                io.write(pack(fmt, *dump(value)))
                io.write(b"\x00" * ((align - (size % align)) % align))
            else:
                return value

        return cs.with_info_before_validator_function(
            validator,
            schema=handler(source),
            metadata={_METADATA_KEY: self},
            serialization=cs.plain_serializer_function_ser_schema(serializer, info_arg=True),
        )


_USE_BUFFER = object()


type _Recurse = Callable[[cs.CoreSchema, _Recurse], cs.CoreSchema]


class _ModelSchemaAdapter:
    _VISIT_TYPES: ClassVar[set[cs.CoreSchemaType]] = {
        "tuple",
        "model",
        "definition-ref",
        "model-fields",
    }
    _ALLOWED_TYPES: ClassVar[set[cs.CoreSchemaType]] = {
        "function-before",
        "default",
    }

    def __init__(self, handler: GetCoreSchemaHandler) -> None:
        self.handler = handler
        self.format: list[str] = []
        self.in_ref = False
        self.field_alignments: list[int] = []
        self.visitors: dict[str, _Recurse] = {}
        for schema_type in self._VISIT_TYPES:
            method_name = f"visit_{schema_type.replace('-', '_')}"
            self.visitors[schema_type] = getattr(self, method_name)

    def adapt(self, schema: cs.CoreSchema) -> cs.CoreSchema:
        return walk_core_schema(schema, self.visit)

    def visit(self, schema: cs.CoreSchema, recurse: _Recurse) -> cs.CoreSchema:
        if _get_metadata(schema):
            return schema
        schema_type = schema["type"]
        visit_fn = self.visitors.get(schema_type)
        if visit_fn is not None:
            return visit_fn(schema, recurse)
        elif schema_type in self._ALLOWED_TYPES:
            return recurse(schema, self.visit)
        else:
            msg = f"Unsupported schema type {schema['type']!r} in CModel"
            raise TypeError(msg)

    def visit_tuple(self, schema: cs.TupleSchema, recurse: _Recurse) -> cs.CoreSchema:
        if schema.get("variadic_item_index") is not None:
            msg = "CModel does not support variadic tuples"
            raise ValueError(msg)

        size = len(schema["items_schema"])
        use_buffer = (_USE_BUFFER,) * size

        def before_validator(value: Any) -> Any:
            if value is _USE_BUFFER:
                return use_buffer
            else:
                return value

        return cs.no_info_before_validator_function(
            before_validator,
            schema=recurse(schema, self.visit),
        )

    def visit_model(self, schema: cs.ModelSchema, recurse: _Recurse) -> cs.CoreSchema:
        if not issubclass(schema["cls"], CModel):
            msg = f"All models used in a CModel must inherit from CModel, got {schema['cls']!r}"
            raise TypeError(msg)

        if self.in_ref:
            return schema
        else:
            return recurse(schema, self.visit)

    def visit_model_fields(self, schema: cs.ModelFieldsSchema, recurse: _Recurse) -> cs.CoreSchema:
        for field in schema["fields"].values():
            self.field_alignments.append(0)
            try:
                field["schema"] = recurse(field["schema"], self.visit)
            finally:
                self.field_alignments.pop()
        return schema

    def visit_definition_ref(
        self, schema: cs.DefinitionReferenceSchema, recurse: _Recurse
    ) -> cs.CoreSchema:
        resolved_schema = self.handler.resolve_ref_schema(schema)

        self.in_ref = True
        try:
            recurse(resolved_schema, self.visit)
        finally:
            self.in_ref = False

        # Return the ref - no need to duplicated it
        return schema


class _Context(TypedDict):
    io: BytesIO
    align: int


@overload
def _get_context(
    info: ValidationInfo | SerializationInfo, *, required: Literal[True]
) -> _Context: ...


@overload
def _get_context(
    info: ValidationInfo | SerializationInfo, *, required: bool = ...
) -> _Context | None: ...


def _get_context(
    info: ValidationInfo | SerializationInfo, *, required: bool = False
) -> _Context | None:
    ctx = info.context.get(_CONTEXT_KEY) if isinstance(info.context, dict) else None
    if ctx is None and required:
        msg = "Context is required for CModel packing/unpacking"
        raise ValueError(msg)
    return ctx


def _get_metadata(schema: cs.CoreSchema) -> CFmt:
    return schema.get("metadata", {}).get(_METADATA_KEY, {})


_CONTEXT_KEY = "cmodel"
_METADATA_KEY = "cmodel"
