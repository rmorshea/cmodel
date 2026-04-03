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

    c_alignment: ClassVar[int]
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
            if "c_alignment" not in cls.__dict__:
                cls.c_alignment = _get_struct_alignment(adapter.member_alignments)
            return schema

    @classmethod
    def c_unpack(cls, buffer: BytesIO) -> Self:
        """Read a C binary data buffer as a packed struct and return an instance of the model."""
        ctx: _Context = {"io": buffer, "alignment": 0}
        return cls.model_validate(_USE_BUFFER, context={_CONTEXT_KEY: ctx})

    def c_pack(self, buffer: BytesIO) -> None:
        """Write the model instance to a C binary data buffer as a packed struct."""
        ctx: _Context = {"io": buffer, "alignment": 0}
        self.model_dump(context={_CONTEXT_KEY: ctx})

    @model_validator(mode="wrap")
    @classmethod
    def _validate_model(
        cls,
        value: Any,
        handler: ModelWrapValidatorHandler,
        info: cs.ValidationInfo,
    ) -> "CModel":
        if ctx := _get_context(info):
            old_align = cls.c_alignment
            ctx["alignment"] = cls.c_alignment
            try:
                return handler(value)
            finally:
                ctx["alignment"] = old_align
        else:
            return value

    @model_serializer(mode="wrap")
    def _serialize_model(
        self, handler: SerializerFunctionWrapHandler, info: cs.SerializationInfo
    ) -> Any:
        if ctx := _get_context(info) and isinstance(self, CModel):
            # Update the alignment for fields in this model.
            ctx = _get_context(info, required=True)
            old_align = self.c_alignment
            ctx["alignment"] = self.c_alignment
            try:
                return handler(self)
            finally:
                ctx["alignment"] = old_align
        else:
            return handler(self)


@dataclass
class CFmt[T]:
    """Metadata for a C field, used in the Annotated type of each field in a CModel."""

    fmt: str
    validate: Callable[[tuple[Any, ...]], T] = lambda x: x  # pyright: ignore[reportAssignmentType]
    dump: Callable[[T], tuple[Any, ...]] = lambda x: x  # pyright: ignore[reportAssignmentType]

    def __post_init__(self) -> None:
        if self.fmt.startswith(("@", "=", "<", ">", "!")):
            msg = "Format string should not include byte order or alignment characters"
            raise ValueError(msg)

    @property
    def alignment(self) -> int:
        """Calculate the alignment of this annotated type based on the format string."""
        return _get_struct_alignment([calcsize(s) for s in self.fmt if not s.isdigit()])

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
                alignment = ctx["alignment"]
                value = unpack_from(fmt, io.getbuffer(), io.tell())
                io.seek(size + (alignment - (size % alignment)) % alignment, 1)
                return validate(value)
            else:
                return value

        def serializer(value: Any, info: SerializationInfo) -> Any:
            if ctx := _get_context(info):
                io = ctx["io"]
                alignment = ctx["alignment"]
                io.write(pack(fmt, *dump(value)))
                io.write(b"\x00" * ((alignment - (size % alignment)) % alignment))
            return value

        schema = handler(source)

        return cs.with_info_before_validator_function(
            validator,
            schema=schema,
            metadata={_METADATA_KEY: self},
            serialization=cs.plain_serializer_function_ser_schema(
                serializer,
                info_arg=True,
                return_schema=schema,
            ),
        )


_USE_BUFFER = object()


type _Recurse = Callable[[cs.CoreSchema, _Recurse], cs.CoreSchema]


class _ModelSchemaAdapter:
    _VISIT_TYPES: ClassVar[set[cs.CoreSchemaType]] = {
        "definition-ref",
        "function-before",
        "function-wrap",
        "model-fields",
        "model",
        "tuple",
    }
    _ALLOWED_TYPES: ClassVar[set[cs.CoreSchemaType]] = {
        "default",
        "any",
    }

    def __init__(self, handler: GetCoreSchemaHandler) -> None:
        self.handler = handler
        self.format: list[str] = []
        self.in_ref = False
        self.member_alignments: list[int] = []
        self.visitors: dict[str, _Recurse] = {}
        for schema_type in self._VISIT_TYPES:
            method_name = f"visit_{schema_type.replace('-', '_')}"
            self.visitors[schema_type] = getattr(self, method_name)

    def adapt(self, schema: cs.CoreSchema) -> cs.CoreSchema:
        return walk_core_schema(schema, self.visit)

    def visit(self, schema: cs.CoreSchema, recurse: _Recurse) -> cs.CoreSchema:
        if cfmt := _get_cfmt(schema):
            self.member_alignments.append(cfmt.alignment)
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
            field["schema"] = self.visit(field["schema"], recurse)
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

    def visit_function_before(
        self, schema: cs.BeforeValidatorFunctionSchema, recurse: _Recurse
    ) -> cs.CoreSchema:
        return self.visit(schema["schema"], recurse)

    def visit_function_wrap(
        self, schema: cs.WrapValidatorFunctionSchema, recurse: _Recurse
    ) -> cs.CoreSchema:
        return self.visit(schema["schema"], recurse)


def _get_struct_alignment(member_alignments: list[int]) -> int:
    """Calculate the alignment of a struct based on the alignments of its members.

    From: https://stackoverflow.com/questions/14510711/how-is-the-size-of-a-c-class-determined/14510919#14510919

    * Each member in the structure has some size s and some alignment requirement a.
    * The compiler starts with a size S set to zero and an alignment requirement
      A set to one (byte).
    * The compiler processes each member in the structure in order:
        1. Consider the member's alignment requirement a. If S is not currently a multiple of
           a, then add just enough bytes to S so that it is a multiple of a. This determines where
           the member will go; it will go at offset S from the beginning of the structure (for the
           current value of S).
        2. Set A to the least common multiple1 of A and a.
        3. Add s to S, to set aside space for the member.
    * When the above process is done for each member, consider the structure's alignment
      requirement A. If S is not currently a multiple of A, then add just enough to S so that
      it is a multiple of A.

    This can be simplified to just taking the maximum alignment of the members.
    """
    return max(member_alignments, default=1)


class _Context(TypedDict):
    io: BytesIO
    alignment: int


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


def _get_cfmt(schema: cs.CoreSchema) -> CFmt | None:
    return schema.get("metadata", {}).get(_METADATA_KEY)


_CONTEXT_KEY = "cmodel"
_METADATA_KEY = "cmodel"
