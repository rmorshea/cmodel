# Model common structs

Most CModel usage starts with three building blocks:

- scalar fields such as integers and floats
- nested structs
- fixed-size repeated values

This guide shows how to combine them without getting into internal details.

## Use the built-in field aliases

The [`cmodel.types`][cmodel.types] module provides aliases for common C scalar formats.

```python
from cmodel import CModel
from cmodel.types import Bool
from cmodel.types import Float
from cmodel.types import Int
from cmodel.types import UnsignedShort


class SensorReading(CModel):
    sensor_id: UnsignedShort
    enabled: Bool
    reading: Float
    sequence: Int
```

These aliases are ordinary Python types wrapped with format metadata. You still get
Pydantic validation on input and model instances on output.

## Nest models to nest structs

If one C struct contains another, model it with another [`CModel`][cmodel.base.CModel] subclass.

```python
class Point(CModel):
    x: Int
    y: Int


class Line(CModel):
    start: Point
    end: Point
```

Packing `Line` writes `start` first and `end` second. Unpacking does the reverse and
returns nested `Point` instances.

## Represent fixed-size repeated values

For repeated values, use `typing.Annotated` with one of the counted format helpers such as [`c_int`][cmodel.types.c_int] or [`c_float`][cmodel.types.c_float].

```python
from typing import Annotated

from cmodel.types import c_float
from cmodel.types import c_int


class Triangle(CModel):
    vertex_ids: Annotated[tuple[int, int, int], c_int(3)]
    normal: Annotated[tuple[float, float, float], c_float(3)]
```

The field type stays explicit in Python, and the binary layout stays explicit in the
format helper.

## Store fixed-length byte strings

Use [`c_char(count)`][cmodel.types.c_char] when the binary layout is a fixed number of bytes.

```python
from typing import Annotated

from cmodel.types import c_char


class Header(CModel):
    magic: Annotated[bytes, c_char(4)]
```

That field packs exactly four bytes. It does not behave like a Python string; it is a
fixed-length byte buffer.

## Round-trip a model

```python
from io import BytesIO


reading = SensorReading(sensor_id=7, enabled=True, reading=1.5, sequence=42)

buf = BytesIO()
reading.c_pack(buf)

buf.seek(0)
decoded = SensorReading.c_unpack(buf)

assert decoded == reading
```

Use this pattern when you are checking that your model matches an existing C layout.

## When to move on

This guide is enough when your structs use native scalar types and straightforward
nested layouts. If your bytes must match a packed struct or a specific ABI boundary,
continue to [Control alignment and layout](control-alignment-and-layout.md).
