"""Public field aliases and helpers for common C-compatible scalar formats."""

import operator
from collections.abc import Callable
from typing import Annotated as An
from uuid import UUID

from cmodel.base import CEncoded
from cmodel.base import CFormat
from cmodel.schema import CEncoderSchema


def _make_one_or_many[T](_: type[T], fmt: str) -> Callable[[int], CFormat[T]]:
    return lambda count: (
        CFormat[T](fmt, operator.itemgetter(0), lambda x: (x,))
        if count == 1
        else CFormat[T](format=f"{count}{fmt}")  # pyright: ignore[reportArgumentType]
    )


c_signed_char = _make_one_or_many(int, "b")
"""Annotated metadata for one or more signed chars. `count>1` represents a tuple of values."""
type SignedChar = An[int, c_signed_char(1)]
"""C format for a single signed char."""

c_unsigned_char = _make_one_or_many(int, "B")
"""Annotated metadata for one or more unsigned chars. `count>1` represents a tuple of values."""
type UnsignedChar = An[int, c_unsigned_char(1)]
"""C format for a single unsigned char."""

c_bool = _make_one_or_many(bool, "?")
"""Annotated metadata for one or more bools. `count>1` represents a tuple of values."""
type Bool = An[bool, c_bool(1)]
"""C format for a single bool."""

c_short = _make_one_or_many(int, "h")
"""Annotated metadata for one or more shorts. `count>1` represents a tuple of values."""
type Short = An[int, c_short(1)]
"""C format for a single short."""

c_unsigned_short = _make_one_or_many(int, "H")
"""Annotated metadata for one or more unsigned shorts. `count>1` represents a tuple of values."""
type UnsignedShort = An[int, c_unsigned_short(1)]
"""C format for a single unsigned short."""

c_int = _make_one_or_many(int, "i")
"""Annotated metadata for one or more ints. `count>1` represents a tuple of values."""
type Int = An[int, c_int(1)]
"""C format for a single int."""

c_unsigned_int = _make_one_or_many(int, "I")
"""Annotated metadata for one or more unsigned ints. `count>1` represents a tuple of values."""
type UnsignedInt = An[int, c_unsigned_int(1)]
"""C format for a single unsigned int."""

c_long = _make_one_or_many(int, "l")
"""Annotated metadata for one or more longs. `count>1` represents a tuple of values."""
type Long = An[int, c_long(1)]
"""C format for a single long."""

c_unsigned_long = _make_one_or_many(int, "L")
"""Annotated metadata for one or more unsigned longs. `count>1` represents a tuple of values."""
type UnsignedLong = An[int, c_unsigned_long(1)]
"""C format for a single unsigned long."""

c_long_long = _make_one_or_many(int, "q")
"""Annotated metadata for one or more long longs. `count>1` represents a tuple of values."""
type LongLong = An[int, c_long_long(1)]
"""C format for a single long long."""

c_unsigned_long_long = _make_one_or_many(int, "Q")
"""Annotated metadata for unsigned long longs. `count>1` represents a tuple of values."""
type UnsignedLongLong = An[int, c_unsigned_long_long(1)]
"""C format for a single unsigned long long."""

c_ssize_t = _make_one_or_many(int, "n")
"""Annotated metadata for one or more ssize_t values. `count>1` represents a tuple of values."""
type SSizeT = An[int, c_ssize_t(1)]
"""C format for a single ssize_t."""

c_size_t = _make_one_or_many(int, "N")
"""Annotated metadata for one or more size_t values. `count>1` represents a tuple of values."""
type SizeT = An[int, c_size_t(1)]

c_float = _make_one_or_many(float, "f")
"""Annotated metadata for one or more floats. `count>1` represents a tuple of values."""
type Float = An[float, c_float(1)]
"""C format for a single float."""

c_double = _make_one_or_many(float, "d")
"""Annotated metadata for one or more doubles. `count>1` represents a tuple of values."""
type Double = An[float, c_double(1)]
"""C format for a single double."""

c_complex_float = _make_one_or_many(complex, "F")
"""Annotated metadata for one or more complex floats. `count>1` represents a tuple of values."""
type ComplexFloat = An[complex, c_complex_float(1)]
"""C format for a single complex float."""

c_complex_double = _make_one_or_many(complex, "D")
"""Annotated metadata for one or more complex doubles. `count>1` represents a tuple of values."""
type ComplexDouble = An[complex, c_complex_double(1)]
"""C format for a single complex double."""


def c_uuid() -> CFormat[UUID]:
    """Annotated metadata for a single UUID. Expects 16-byte char array."""
    return CFormat(format="16s", validate=lambda x: UUID(bytes=x[0]), dump=lambda x: (x.bytes,))


type Uuid = An[UUID, c_uuid()]
"""C format for a single UUID."""


def c_char(count: int) -> CFormat:
    """Annotated metadata for a char array of the given length. Returns Python `bytes`."""
    return CFormat(format=f"{count}s", validate=operator.itemgetter(0), dump=lambda x: (x,))


type RawBytes = An[
    bytes,
    CEncoded(
        get_encoder=lambda e, s: CEncoderSchema[bytes](
            type="encoder",
            alignment=1,
            size=None,
            unpack=lambda buffer, _: buffer.read(),
            pack=lambda buffer, value, _: buffer.write(value),
            schema_equality_info=(__name__, "ByteArray"),
        )
    ),
]
"""Raw trailing bytes that consume all remaining data in the buffer.

Should be the last field in a model, as it reads from the current
position to the end of the buffer.
"""
