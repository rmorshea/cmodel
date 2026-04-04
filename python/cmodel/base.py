from collections.abc import Callable
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from struct import calcsize
from struct import pack
from struct import unpack_from
from typing import Any
from typing import ClassVar
from typing import Self

from pydantic import BaseModel
from pydantic import GetCoreSchemaHandler
from pydantic import SerializationInfo
from pydantic import ValidationInfo
from pydantic_core import core_schema as cs
from pydantic_walk_core_schema import walk_core_schema


class CModel(BaseModel):
    """Base class for models that can be packed/unpacked to/from C binary data."""

    c_schema: ClassVar[CSchema]

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
            visitor = _ModelSchemaVisitor(handler)
            schema = visitor.visit(handler(source))
            cls.c_schema = schema
            return schema

    @classmethod
    def c_unpack(cls, buffer: BytesIO) -> Self:
        """Read a C binary data buffer as a packed struct and return an instance of the model."""
        ctx: _Context = {"io": buffer}
        return cls.model_validate(_USE_BUFFER, context={_CONTEXT_KEY: ctx})

    def c_pack(self, buffer: BytesIO) -> None:
        """Write the model instance to a C binary data buffer as a packed struct."""
        ctx: _Context = {"io": buffer}
        self.model_dump(context={_CONTEXT_KEY: ctx})


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

    def __get_pydantic_core_schema__(
        self,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> cs.CoreSchema:
        fmt = self.fmt
        validate = self.validate
        dump = self.dump

        def validator(value: Any, info: ValidationInfo) -> Any:
            if value is _USE_BUFFER:
                ctx = _get_context(info, required=True)
                io = ctx["io"]
                value = unpack_from(fmt, io.getbuffer(), io.tell())
                return validate(value)
            else:
                return value

        def serializer(value: Any, info: SerializationInfo) -> Any:
            if ctx := _get_context(info):
                ctx["io"].write(pack(fmt, *dump(value)))
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


class _ModelSchemaVisitor:
    _VISIT_TYPES: ClassVar[set[cs.CoreSchemaType]] = {
        "definition-ref",
        "function-before",
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
        self.visitors: dict[str, _Recurse] = {}
        for schema_type in self._VISIT_TYPES:
            method_name = f"visit_{schema_type.replace('-', '_')}"
            self.visitors[schema_type] = getattr(self, method_name)

    def visit(self, schema: cs.CoreSchema) -> cs.CoreSchema:
        return walk_core_schema(schema, self.visit_any)

    def visit_any(self, schema: cs.CoreSchema, recurse: _Recurse) -> cs.CoreSchema:
        if cfmt := _get_cfmt(schema):
            # Update the shared alignment of this model with the alignment of this field
            self.alignment.set(_get_fmt_alignment(cfmt.fmt))
            return schema
        schema_type = schema["type"]
        visit_fn = self.visitors.get(schema_type)
        if visit_fn is not None:
            return visit_fn(schema, recurse)
        elif schema_type in self._ALLOWED_TYPES:
            return recurse(schema, self.visit_any)
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

        # tuples are treated like anonymous structs so they have their own alignment
        with self._fresh_alignment():
            schema = recurse(schema, self.visit_any)  # pyright: ignore[reportAssignmentType]
            schema["items_schema"] = [
                _add_alignment_handling_to_field_schema(i, self.alignment)
                for i in schema["items_schema"]
            ]
            return cs.no_info_before_validator_function(before_validator, schema=schema)

    def visit_model(self, schema: cs.ModelSchema, recurse: _Recurse) -> cs.CoreSchema:
        if not issubclass(schema["cls"], CModel):
            msg = f"All models used in a CModel must inherit from CModel, got {schema['cls']!r}"
            raise TypeError(msg)

        if self.in_ref:
            return schema
        else:
            with self._fresh_alignment():
                return recurse(schema, self.visit_any)

    def visit_model_fields(self, schema: cs.ModelFieldsSchema, recurse: _Recurse) -> cs.CoreSchema:
        for f in schema["fields"].values():
            f["schema"] = _add_alignment_handling_to_field_schema(
                self.visit_any(f["schema"], recurse),
                self.alignment,
            )
        return schema

    def visit_definition_ref(
        self, schema: cs.DefinitionReferenceSchema, recurse: _Recurse
    ) -> cs.CoreSchema:
        resolved_schema = self.handler.resolve_ref_schema(schema)

        self.in_ref = True
        try:
            recurse(resolved_schema, self.visit_any)
        finally:
            self.in_ref = False

        # Return the ref - no need to duplicated it
        return schema

    def visit_function_before(
        self, schema: cs.BeforeValidatorFunctionSchema, recurse: _Recurse
    ) -> cs.CoreSchema:
        schema["schema"] = self.visit_any(schema["schema"], recurse)
        return schema

    @contextmanager
    def _fresh_alignment(self) -> Iterator[None]:
        last_alignment = self.alignment
        self.alignment = _Alignment()
        try:
            yield
        finally:
            self.alignment = last_alignment


def _get_cfmt(schema: cs.CoreSchema) -> CFmt | None:
    return schema.get("metadata", {}).get(_METADATA_KEY)


def _get_fmt_alignment(fmt: str) -> int:
    return max((calcsize(part) for part in fmt.split() if part.isalpha()), default=1)


_METADATA_KEY = "cmodel"
