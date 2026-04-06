"""Public base classes for defining C-compatible Pydantic models."""

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from typing import ClassVar
from typing import Self
from typing import Unpack

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema as cs

from cmodel import _utils
from cmodel.schema import CStructSchema
from cmodel.schema import EndianType
from cmodel.schema import SizeType
from cmodel.schema import c_schema_from_pydantic_core_schema
from cmodel.schema import pack_c_schema
from cmodel.schema import unpack_c_schema


class CModel(BaseModel):
    """Base class for models that can be packed to and unpacked from C-compatible bytes.

    Subclasses behave like normal Pydantic models, but also carry a derived binary
    schema that [`c_pack()`][cmodel.base.CModel.c_pack] and
    [`c_unpack()`][cmodel.base.CModel.c_unpack] use to read and write struct data.
    """

    c_schema: ClassVar[CStructSchema]
    """The C struct schema for this model, derived from the Pydantic schema of the model"""
    c_alignment: ClassVar[int] = 0
    """Override the alignment of this struct. Native by default (0)."""
    c_endian_type: ClassVar[EndianType] = "native"
    """Override the endianness of this struct. Native by default."""
    c_size_type: ClassVar[SizeType] = "native"
    """Override the size type of this struct. Native by default."""

    def __init_subclass__(
        cls,
        *,
        c_alignment: int | None = None,
        c_endian_type: EndianType | None = None,
        c_size_type: SizeType | None = None,
        **kwargs: Unpack[ConfigDict],
    ) -> None:
        super().__init_subclass__(**kwargs)
        if c_alignment is not None:
            cls.c_alignment = c_alignment
        if c_endian_type is not None:
            cls.c_endian_type = c_endian_type
        if c_size_type is not None:
            cls.c_size_type = c_size_type

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
            py_schema = handler(source)
            c_schema = c_schema_from_pydantic_core_schema(py_schema, handler)
            if c_schema["type"] != "struct":
                msg = "CModel fields must be structs"
                raise TypeError(msg)
            cls.c_schema = c_schema
            return py_schema

    @classmethod
    def c_unpack(cls, buffer: BytesIO) -> Self:
        """Read one model instance from the current position of a binary buffer."""
        value = unpack_c_schema(buffer, cls.c_schema)
        return cls.model_validate(value)

    def c_pack(self, buffer: BytesIO) -> None:
        """Write this model instance to the current position of a binary buffer."""
        value = self.model_dump()
        pack_c_schema(buffer, self.c_schema, value)


@dataclass
class CFormat[T]:
    """Binary format metadata for a field declared with `typing.Annotated`.

    `format` is a `struct`-style format string for the field itself. Optional
    `validate` and `dump` callables adapt between the raw tuple produced by `struct`
    operations and the Python value stored on the model. Attach it to a field with
    `Annotated[..., CFormat(...)]`, or use helpers from [`cmodel.types`][cmodel.types]
    for the common scalar cases.
    """

    format: str
    validate: Callable[[tuple[Any, ...]], T] = lambda x: x  # pyright: ignore[reportAssignmentType]
    dump: Callable[[T], tuple[Any, ...]] = lambda x: x  # pyright: ignore[reportAssignmentType]

    def __post_init__(self) -> None:
        if self.format.startswith(("@", "=", "<", ">", "!")):
            msg = "Format string should not include byte order or alignment characters"
            raise ValueError(msg)
        current_char = ""
        for char in self.format:
            if char.isalpha():
                if not current_char:
                    current_char = char
                elif current_char != char:
                    # We enforce this because of how the endian formatting characters remove
                    # padding between fields. If multiple types
                    msg = "Format string must only contain one type of format character"
                    raise ValueError(msg)

    def __get_pydantic_core_schema__(
        self,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> cs.CoreSchema:
        schema = handler(source)
        _utils.set_pydantic_schema_metadata(
            schema,
            {
                "format": self.format,
                "validate": self.validate,
                "dump": self.dump,
            },
        )
        return schema
