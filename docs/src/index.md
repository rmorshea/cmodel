# CModel

Model C structs with Pydantic.

CModel is for the case where your Python program needs to read or write a binary
layout that already exists in C. You define the layout once as a Pydantic model,
validate data with normal Python types, then pack or unpack bytes with
[`c_pack()`][cmodel.base.CModel.c_pack] and [`c_unpack()`][cmodel.base.CModel.c_unpack].

## Simple Structs

Install the package:

```bash
pip install cmodel
```

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

That is the core workflow:

1. Describe the binary layout with a [`CModel`][cmodel.base.CModel] subclass.
1. Use [`cmodel.types`][cmodel.types] aliases, or `Annotated[..., CFmt(...)]`, to control field formats.
1. Call [`c_pack()`][cmodel.base.CModel.c_pack] to write bytes.
1. Call [`c_unpack()`][cmodel.base.CModel.c_unpack] to read bytes.

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
    coords: Annotated[tuple[int, int, int], c_int(3)]
```

If you need a packed layout with no implicit alignment padding, set [`c_alignment`][cmodel.base.CModel.c_alignment] to `1`:

```python
class PackedReading(CModel, c_alignment=1):
    count: Int
    valid: bool
    value: Float
```

## What to read next

- If you want to model common field shapes, start with [Model common structs](guides/model-common-structs.md).
- If you need exact byte layout, read [Control alignment and layout](guides/control-alignment-and-layout.md).
- If the built-in field aliases are not enough, use [Define custom field formats](guides/define-custom-field-formats.md).
- If you want the design rationale, read [How CModel maps Python models to C layouts](explanation/how-cmodel-maps-python-models-to-c-layouts.md).
- If you already know what you need, jump to the [API reference](reference/SUMMARY.md).
