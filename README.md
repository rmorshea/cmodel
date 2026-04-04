# CModel

[![PyPI - Version](https://img.shields.io/pypi/v/cmodel.svg)](https://pypi.org/project/cmodel)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cmodel.svg)](https://pypi.org/project/cmodel)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Model C structs with Pydantic

`cmodel` lets you describe C-compatible binary layouts with normal Pydantic models.
You keep Pydantic's validation and nested models, and gain a simple way to pack and
unpack structs from binary buffers.

## Quick start

```python
from io import BytesIO

from cmodel import CModel
from cmodel.types import Int


class Point(CModel):
	x: Int
	y: Int


buf = BytesIO()
Point(x=3, y=7).c_pack(buf)

buf.seek(0)
point = Point.c_unpack(buf)

assert point == Point(x=3, y=7)
assert buf.getvalue() == b"\x03\x00\x00\x00\x07\x00\x00\x00"
```

## What CModel provides

- Typed field aliases for common C scalar formats such as `Int`, `Float`, and `Bool`
- Repeated field formats such as `Annotated[tuple[int, int, int], c_int(3)]`
- Nested structs by nesting `CModel` subclasses
- Explicit packed layouts with `c_alignment=1`
- Custom field encodings with `CFmt`

## Documentation

The documentation site includes:

- A guided first example for getting started
- Practical guides for layout control and custom formats
- API reference for the public modules
- Conceptual explanation of how Pydantic validation maps to binary layout
