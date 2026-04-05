"""Public field aliases and helpers for common C-compatible scalar formats."""

import operator
from collections.abc import Callable
from typing import Annotated as An
from uuid import UUID

from cmodel.base import CFmt


def _make_one_or_many[T](_: type[T], fmt: str) -> Callable[[int], CFmt[T]]:
    return lambda count: (
        CFmt[T](fmt, operator.itemgetter(0), lambda x: (x,))
        if count == 1
        else CFmt[T](format=f"{count}{fmt}")  # pyright: ignore[reportArgumentType]
    )


c_signed_char = _make_one_or_many(int, "b")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more signed chars. For `count=1` the value is returned as an int."""
SignedChar = An[int, c_signed_char(1)]
"""C format for a single signed char."""

c_unsigned_char = _make_one_or_many(int, "B")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more unsigned chars. For `count=1` the value is returned as an int."""
UnsignedChar = An[int, c_unsigned_char(1)]
"""C format for a single unsigned char."""

c_bool = _make_one_or_many(bool, "?")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more bools. For `count=1` the value is returned as a bool."""
Bool = An[bool, c_bool(1)]
"""C format for a single bool."""

c_short = _make_one_or_many(int, "h")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more shorts. For `count=1` the value is returned as an int."""
Short = An[int, c_short(1)]
"""C format for a single short."""

c_unsigned_short = _make_one_or_many(int, "H")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more unsigned shorts. For `count=1` the value is returned as an int."""
UnsignedShort = An[int, c_unsigned_short(1)]
"""C format for a single unsigned short."""

c_int = _make_one_or_many(int, "i")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more ints. For `count=1` the value is returned as an int."""
Int = An[int, c_int(1)]
"""C format for a single int."""

c_unsigned_int = _make_one_or_many(int, "I")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more unsigned ints. For `count=1` the value is returned as an int."""
UnsignedInt = An[int, c_unsigned_int(1)]
"""C format for a single unsigned int."""

c_long = _make_one_or_many(int, "l")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more longs. For `count=1` the value is returned as an int."""
Long = An[int, c_long(1)]
"""C format for a single long."""

c_unsigned_long = _make_one_or_many(int, "L")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more unsigned longs. For `count=1` the value is returned as an int."""
UnsignedLong = An[int, c_unsigned_long(1)]
"""C format for a single unsigned long."""

c_float = _make_one_or_many(float, "f")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more floats. For `count=1` the value is returned as a float."""
Float = An[float, c_float(1)]
"""C format for a single float."""

c_double = _make_one_or_many(float, "d")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more doubles. For `count=1` the value is returned as a float."""
Double = An[float, c_double(1)]
"""C format for a single double."""

c_complex_float = _make_one_or_many(complex, "F")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more complex floats. For `count=1` the value is returned as a complex."""
ComplexFloat = An[complex, c_complex_float(1)]
"""C format for a single complex float."""

c_complex_double = _make_one_or_many(complex, "D")
"""[`CFmt`][cmodel.base.CFmt] helper for one or more complex doubles. For `count=1` the value is returned as a complex."""
ComplexDouble = An[complex, c_complex_double(1)]
"""C format for a single complex double."""


def c_uuid() -> CFmt[UUID]:
    """[`CFmt`][cmodel.base.CFmt] helper for a UUID, represented as a 16-byte array."""
    return CFmt(format="16s", validate=lambda x: UUID(bytes=x[0]), dump=lambda x: (x.bytes,))


Uuid = An[UUID, c_uuid()]
"""C format for a single UUID."""


def c_char(count: int) -> CFmt:
    """[`CFmt`][cmodel.base.CFmt] helper for a char array of the given count."""
    return CFmt(format=f"{count}s", validate=operator.itemgetter(0), dump=lambda x: (x,))
