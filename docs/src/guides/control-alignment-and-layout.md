# Control alignment and layout

The fastest way to get incorrect binary data is to assume the layout has no padding.
[`CModel`][cmodel.base.CModel] lets you keep the default aligned behavior, or opt into packed layouts when the
target format requires it.

Alignment and byte order are separate concerns:

- [`c_alignment`][cmodel.base.CModel.c_alignment] controls padding and field placement in the struct layout.
- The `endian` argument to [`c_pack()`][cmodel.base.CModel.c_pack] and [`c_unpack()`][cmodel.base.CModel.c_unpack] controls byte order when bytes
    are written or read.

## Understand the default

By default, [`CModel`][cmodel.base.CModel] derives a struct alignment from the fields in the model. That means
some layouts will include padding bytes between fields.

```python
from cmodel import CModel
from cmodel.types import Bool
from cmodel.types import Float
from cmodel.types import Int


class Mixed(CModel):
    count: Int
    flag: Bool
    value: Float
```

On a typical native layout, `value` will be aligned after `flag`, so the packed bytes
are not simply `int` + `bool` + `float` back to back.

By default, [`c_pack()`][cmodel.base.CModel.c_pack] and [`c_unpack()`][cmodel.base.CModel.c_unpack] use `endian="="`, which selects native byte
order. It affects how multi-byte fields are encoded, but it does not change where
padding bytes appear and it does not enable native struct alignment rules.

## Use packed layout when the bytes are contiguous

Set [`c_alignment`][cmodel.base.CModel.c_alignment] to `1` on the model class when the target binary format is packed.

```python
class PackedMixed(CModel, c_alignment=1):
    count: Int
    flag: Bool
    value: Float
```

Now [`CModel`][cmodel.base.CModel] writes each field immediately after the previous one with no alignment
padding inserted.

## Compare the two layouts

```python
from io import BytesIO


aligned = BytesIO()
Mixed(count=5, flag=True, value=1.5).c_pack(aligned, endian="<")

packed = BytesIO()
PackedMixed(count=5, flag=True, value=1.5).c_pack(packed, endian="<")

assert aligned.getvalue() != packed.getvalue()
```

When you are integrating with an existing binary protocol, this kind of comparison is a
good first check.

Use an explicit `endian` value in examples like this when you want the byte sequence to
be stable across machines.

## Choose byte order separately from alignment

Pass `endian` to [`c_pack()`][cmodel.base.CModel.c_pack] and [`c_unpack()`][cmodel.base.CModel.c_unpack] when the binary format requires a specific
byte order.

In particular, `endian="="` only selects native byte order. Alignment still comes from
the model's layout rules and any [`c_alignment`][cmodel.base.CModel.c_alignment] value on the struct.

```python
buf = BytesIO()

PackedMixed(count=5, flag=True, value=1.5).c_pack(buf, endian=">")

buf.seek(0)
decoded = PackedMixed.c_unpack(buf, endian=">")

assert decoded == PackedMixed(count=5, flag=True, value=1.5)
```

The important distinction is:

- [`c_alignment`][cmodel.base.CModel.c_alignment] set to `1` changes the layout by removing padding between fields.
- `endian=">"` changes the byte order of multi-byte values but not the alignment.
- These settings are independent, so you can have an aligned big-endian struct or a
    packed little-endian struct.

## Choose alignment per struct

Alignment is attached to each model class, not to the entire process. That makes it
practical to mix layouts when one nested struct is packed and another is naturally
aligned.

```python
class Header(CModel, c_alignment=1):
    kind: Int
    length: Int


class Payload(CModel):
    value: Float
    ready: Bool


class Packet(CModel):
    header: Header
    payload: Payload
```

In that example, `Header` uses a packed layout and `Payload` uses its own default
alignment rules.

Byte order is still chosen when packing or unpacking:

```python
buf = BytesIO()
Packet(
    header=Header(kind=1, length=8),
    payload=Payload(value=1.5, ready=True),
).c_pack(buf, endian="<")
```

## Keep the model close to the source layout

If you already have a C declaration, mirror its field order exactly and decide on
alignment immediately. Do not treat padding as an afterthought.

Then decide which byte order the protocol uses and pass that same `endian` value to both
[`c_pack()`][cmodel.base.CModel.c_pack] and [`c_unpack()`][cmodel.base.CModel.c_unpack].

Use this guide when you know the bytes you need to match. If the missing piece is an
unusual field encoding rather than padding, continue to
[Define custom field formats](define-custom-field-formats.md).
