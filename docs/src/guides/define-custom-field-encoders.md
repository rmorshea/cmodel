# Define custom field encoders

Use [`CEncoded`][cmodel.base.CEncoded] when you need full control over how a field is
read from and written to a binary buffer. Unlike [`CFormat`][cmodel.base.CFormat],
which wraps Python's `struct` module, [`CEncoded`][cmodel.base.CEncoded] lets you
supply your own pack and unpack functions directly.

## When to reach for CEncoded

[`CFormat`][cmodel.base.CFormat] covers the common case — fixed-size fields described
by a `struct` format string. Reach for [`CEncoded`][cmodel.base.CEncoded] when:

- the field has **variable length** (size not known until read time)
- the binary encoding is **not expressible** as a `struct` format string
- you need to **control raw I/O** against the buffer yourself

## Use the built-in RawBytes alias

The simplest [`CEncoded`][cmodel.base.CEncoded] field is
[`RawBytes`][cmodel.types.RawBytes], which reads all remaining bytes in the buffer.
Place it as the last field in a model.

```python
from cmodel import CModel
from cmodel.types import RawBytes


class Packet(CModel):
    header: int
    data: RawBytes
```

After unpacking, `data` contains everything after `header`. When packing, the raw bytes
are written as-is.

## Define a custom encoder

[`CEncoded`][cmodel.base.CEncoded] takes a single argument: `get_encoder`, a factory
function called with the struct's [`EndianType`][cmodel.schema.EndianType] and
[`SizeType`][cmodel.schema.SizeType]. It must return a
[`CEncoderSchema`][cmodel.schema.CEncoderSchema] dict.

```python
from typing import Annotated

from cmodel import CEncoded
from cmodel import CModel
from cmodel.schema import CEncoderSchema, CBuildContext, SizeRange


def uint24(build_ctx: CBuildContext) -> CEncoderSchema[int]:
    byteorder = "little" if build_ctx["endian_type"] in ("native", "little") else "big"

    def unpack(buf, _unpack_ctx):  # don't need the context for fixed-size fields
        return int.from_bytes(buf.read(3), byteorder)

    def pack(buf, value, _pack_ctx):  # don't need the context for fixed-size fields
        buf.write(value.to_bytes(3, byteorder))

    return CEncoderSchema[int](
        type="encoder",
        size=3,
        size_range=SizeRange.FIXED,
        alignment=1,
        unpack=unpack,
        pack=pack,
        schema_equality_info=("example", "uint24", byteorder),
    )


UInt24 = Annotated[int, CEncoded(uint24)]


class AudioSample(CModel):
    left: UInt24
    right: UInt24
```

Python's `struct` module has no format character for a 24-bit integer, but 24-bit
fields are common in audio formats and network protocols. Since the encoding falls
outside what `struct` can express, [`CFormat`][cmodel.base.CFormat] cannot describe it
— exactly the kind of field [`CEncoded`][cmodel.base.CEncoded] is designed for.

## Understand CEncoderSchema fields

The [`CEncoderSchema`][cmodel.schema.CEncoderSchema] dict returned by `get_encoder`
has the following keys:

| Key                    | Type                                | Purpose                                                        |
| ---------------------- | ----------------------------------- | -------------------------------------------------------------- |
| `type`                 | `"encoder"`                         | Must always be `"encoder"`.                                    |
| `size`                 | `int \| None`                       | Byte size of the encoded value, or `None` for variable length. |
| `alignment`            | `int`                               | Alignment requirement in bytes.                                |
| `unpack`               | `(BytesIO, CUnpackContext) -> T`    | Read the value from a buffer.                                  |
| `pack`                 | `(BytesIO, T, CPackContext) -> Any` | Write the value to a buffer.                                   |
| `schema_equality_info` | `Hashable`                          | Used to compare two schemas for equality.                      |

Set `size` to `None` for variable-length fields. A variable-length field should
generally be the last field in a struct, since its `unpack` function may read to the end
of the buffer.

## Respect endianness and size type

The factory function receives the struct's `endian` and `size` arguments so you can
build format strings or choose encoding strategies that match the model's byte order.

```python
class BigEndianSample(CModel, c_endian_type="big"):
    left: UInt24
    right: UInt24
```

The `uint24` factory will be called with `endian="big"`, so it writes the three bytes
in big-endian order.
