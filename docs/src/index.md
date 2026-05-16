# CModel

Model C structs with Pydantic. Define the layout once as a Pydantic model
inheriting from `CModel` and get packing and unpacking for free.

## Installation

CModel can be installed with a simple

```bash
pip install cmodel
```

## Simple Structs

Define a struct as a model:

```python
from cmodel import CModel
from cmodel.types import Int


class Point(CModel):
    x: Int
    y: Int
```

Pack it into bytes:

```python
from io import BytesIO

buf = BytesIO()
Point(x=3, y=7).c_pack(buf)

assert buf.getvalue() == b"\x03\x00\x00\x00\x07\x00\x00\x00"
```

Read it back:

```python
buf.seek(0)
point = Point.c_unpack(buf)

assert point == Point(x=3, y=7)
```

## Nested Structs

Nested structs look like nested models:

```python
from cmodel.types import Float


class Header(CModel):
    version: Int
    count: Int


class Reading(CModel):
    x: Float
    y: Float


class Packet(CModel):
    header: Header
    reading: Reading
```

Repeated values can be expressed with `Annotated` and a counted format helper such as [`c_int`][cmodel.types.c_int]:

```python
from typing import Annotated

from cmodel.types import c_int


class Triangle(CModel):
    x_coords: Annotated[tuple[int, int, int], c_int(3)]
    y_coords: Annotated[tuple[int, int, int], c_int(3)]
```

Variable-length arrays are modeled with variadic tuples. Use
[`CCountedBy`][cmodel.base.CCountedBy] when another field stores the element count:

```python
from cmodel import CCountedBy


class CountedPacket(CModel):
    values_count: Int
    values: Annotated[tuple[int, ...], CCountedBy.template("{}_count")]
```

Or use an unbounded trailing array with `tuple[T, ...]`, which reads until the end of
the buffer:

```python
class TrailingPacket(CModel):
    payload_words: tuple[int, ...]
```

If you need a packed layout with no implicit alignment padding, set [`c_alignment`][cmodel.base.CModel.c_alignment] to `1`:

```python
class PackedReading(CModel, c_alignment=1):
    count: Int
    valid: bool
    value: Float
```
