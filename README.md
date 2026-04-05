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
