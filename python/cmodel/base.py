from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from struct import calcsize
from typing import Any
from typing import ClassVar
from typing import Self
from typing import Unpack

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema as cs

from cmodel import _utils
from cmodel.schema import PYDANTIC_SCHEMA_METADATA_KEY
from cmodel.schema import CFormatSchema
from cmodel.schema import CStructSchema
from cmodel.schema import PydanticSchemaMetadata
from cmodel.schema import c_schema_from_pydantic_core_schema
from cmodel.schema import pack_c_schema
from cmodel.schema import unpack_c_schema


class CModel(BaseModel):
    """Base class for models that can be packed/unpacked to/from C binary data."""

    c_schema: ClassVar[CStructSchema]
    c_alignment: ClassVar[int | None] = None

    def __init_subclass__(
        cls, *, c_alignment: int | None = None, **kwargs: Unpack[ConfigDict]
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls.c_alignment = c_alignment

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
        """Read a C binary data buffer as a packed struct and return an instance of the model."""
        value = unpack_c_schema(buffer, cls.c_schema)
        return cls.model_validate(value)

    def c_pack(self, buffer: BytesIO) -> None:
        """Write the model instance to a C binary data buffer as a packed struct."""
        value = self.model_dump()
        pack_c_schema(buffer, self.c_schema, value)


@dataclass
class CFmt[T]:
    """Metadata for a C field, used in the Annotated type of each field in a CModel."""

    format: str
    validate: Callable[[tuple[Any, ...]], T] = lambda x: x  # pyright: ignore[reportAssignmentType]
    dump: Callable[[T], tuple[Any, ...]] = lambda x: x  # pyright: ignore[reportAssignmentType]

    def __post_init__(self) -> None:
        if self.format.startswith(("@", "=", "<", ">", "!")):
            msg = "Format string should not include byte order or alignment characters"
            raise ValueError(msg)

    def __get_pydantic_core_schema__(
        self,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> cs.CoreSchema:
        schema = handler(source)
        schema.setdefault("metadata", {})[PYDANTIC_SCHEMA_METADATA_KEY] = PydanticSchemaMetadata(
            format_schema=CFormatSchema(
                type="format",
                format=self.format,
                alignment=_utils.calc_format_alignment(self.format),
                validate=self.validate,
                dump=self.dump,
                size=calcsize(self.format),
            )
        )
        return schema
