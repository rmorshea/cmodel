"""Public field aliases and helpers for common C-compatible scalar formats."""

import operator
from collections.abc import Callable
from typing import Annotated as An
from uuid import UUID

from cmodel.base import CFormat


def _make_one_or_many[T](_: type[T], fmt: str) -> Callable[[int], CFormat[T]]:
    return lambda count: (
        CFormat[T](fmt, operator.itemgetter(0), lambda x: (x,))
        if count == 1
        else CFormat[T](format=f"{count}{fmt}")  # pyright: ignore[reportArgumentType]
    )


c_signed_char = _make_one_or_many(int, "b")
"""Annotated metadata for one or more signed chars. `count>1` represents a tuple of values."""
SignedChar = An[int, c_signed_char(1)]
"""C format for a single signed char."""

c_unsigned_char = _make_one_or_many(int, "B")
"""Annotated metadata for one or more unsigned chars. `count>1` represents a tuple of values."""
UnsignedChar = An[int, c_unsigned_char(1)]
"""C format for a single unsigned char."""

c_bool = _make_one_or_many(bool, "?")
"""Annotated metadata for one or more bools. `count>1` represents a tuple of values."""
Bool = An[bool, c_bool(1)]
"""C format for a single bool."""

c_short = _make_one_or_many(int, "h")
"""Annotated metadata for one or more shorts. `count>1` represents a tuple of values."""
Short = An[int, c_short(1)]
"""C format for a single short."""

c_unsigned_short = _make_one_or_many(int, "H")
"""Annotated metadata for one or more unsigned shorts. `count>1` represents a tuple of values."""
UnsignedShort = An[int, c_unsigned_short(1)]
"""C format for a single unsigned short."""

c_int = _make_one_or_many(int, "i")
"""Annotated metadata for one or more ints. `count>1` represents a tuple of values."""
Int = An[int, c_int(1)]
"""C format for a single int."""

c_unsigned_int = _make_one_or_many(int, "I")
"""Annotated metadata for one or more unsigned ints. `count>1` represents a tuple of values."""
UnsignedInt = An[int, c_unsigned_int(1)]
"""C format for a single unsigned int."""

c_long = _make_one_or_many(int, "l")
"""Annotated metadata for one or more longs. `count>1` represents a tuple of values."""
Long = An[int, c_long(1)]
"""C format for a single long."""

c_unsigned_long = _make_one_or_many(int, "L")
"""Annotated metadata for one or more unsigned longs. `count>1` represents a tuple of values."""
UnsignedLong = An[int, c_unsigned_long(1)]
"""C format for a single unsigned long."""

c_float = _make_one_or_many(float, "f")
"""Annotated metadata for one or more floats. `count>1` represents a tuple of values."""
Float = An[float, c_float(1)]
"""C format for a single float."""

c_double = _make_one_or_many(float, "d")
"""Annotated metadata for one or more doubles. `count>1` represents a tuple of values."""
Double = An[float, c_double(1)]
"""C format for a single double."""

c_complex_float = _make_one_or_many(complex, "F")
"""Annotated metadata for one or more complex floats. `count>1` represents a tuple of values."""
ComplexFloat = An[complex, c_complex_float(1)]
"""C format for a single complex float."""

c_complex_double = _make_one_or_many(complex, "D")
"""Annotated metadata for one or more complex doubles. `count>1` represents a tuple of values."""
ComplexDouble = An[complex, c_complex_double(1)]
"""C format for a single complex double."""


def c_uuid() -> CFormat[UUID]:
    """Annotated metadata for a single UUID. Expects 16-byte char array."""
    return CFormat(format="16s", validate=lambda x: UUID(bytes=x[0]), dump=lambda x: (x.bytes,))


Uuid = An[UUID, c_uuid()]
"""C format for a single UUID."""


def c_char(count: int) -> CFormat:
    """Annotated metadata for a char array of the given length. Returns Python `bytes`."""
    return CFormat(format=f"{count}s", validate=operator.itemgetter(0), dump=lambda x: (x,))
