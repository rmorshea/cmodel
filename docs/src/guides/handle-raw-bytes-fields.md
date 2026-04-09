# Handle raw bytes fields

Use [`CRaw`][cmodel.base.CRaw] when a field does not map to a `struct` format string
at all. [`CRaw`][cmodel.base.CRaw] gives you direct control over reading and writing
raw bytes, while still participating in the normal CModel pack and unpack flow.

This is useful when:

- the binary encoding has no `struct` equivalent (e.g. a custom compression or checksum)
- you want to store an opaque blob of known size
- the field consumes the rest of the buffer (variable-length)

## Read and write a fixed-size blob

The simplest case is a field with a known byte count. Provide `size`, `alignment`, and
identity `validate` / `dump` functions to pass bytes through unchanged.

```python
from typing import Annotated

from cmodel import CModel
from cmodel import CRaw
from cmodel.types import Int

FixedBlob = Annotated[
    bytes,
    CRaw(size=4, alignment=1, validate=lambda b: b, dump=lambda b: b),
]


class Packet(CModel):
    header: Int
    data: FixedBlob
```

`data` always reads exactly 4 bytes on unpack and writes exactly 4 bytes on pack. If
the value passed to `dump` does not produce exactly `size` bytes, packing raises a
`ValueError`.

## Adapt raw bytes to a richer Python type

Use `validate` and `dump` to convert between raw bytes and a more convenient Python
representation, just like `validate` and `dump` on [`CFormat`][cmodel.base.CFormat].

```python
from typing import Annotated

from cmodel import CModel
from cmodel import CRaw

HexString = Annotated[
    str,
    CRaw(
        size=4,
        alignment=1,
        validate=lambda b: b.hex(),
        dump=lambda s: bytes.fromhex(s),
    ),
]


class Tag(CModel):
    magic: HexString
```

After unpacking, `magic` is a hex string like `"cafebabe"`. Before packing, the string
is converted back to 4 raw bytes.

## Read the rest of the buffer with a variable-length field

Set `size=None` to consume all remaining bytes in the buffer. Variable-length fields
must be the last field in the struct.

```python
from typing import Annotated

from cmodel import CModel
from cmodel import CRaw
from cmodel.types import Int

VarBytes = Annotated[
    bytes,
    CRaw(size=None, alignment=1, validate=lambda b: b, dump=lambda b: b),
]


class Message(CModel, c_alignment=1):
    length: Int
    payload: VarBytes
```

On unpack, `payload` reads from the current position to the end of the buffer. On pack,
whatever bytes `dump` returns are written directly.

## When to use CRaw versus CFormat

[`CFormat`][cmodel.base.CFormat] works well when the wire encoding maps onto Python's
`struct` format characters. Use [`CRaw`][cmodel.base.CRaw] when:

- the encoding cannot be expressed as a `struct` format string
- you need byte-level control over serialization and deserialization
- the field is an opaque blob that should be passed through untouched

Both annotations follow the same pattern of `validate` for unpacking and `dump` for
packing, so switching between them is straightforward.
