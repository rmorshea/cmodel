# Control alignment and layout

The fastest way to get incorrect binary data is to assume the layout has no padding.
[`CModel`][cmodel.base.CModel] lets you keep the default aligned behavior, or opt into packed layouts when the
target format requires it.

Alignment and byte order are separate concerns:

- [`c_alignment`][cmodel.base.CModel.c_alignment] controls padding and field placement in the struct layout.
- [`c_endian_type`][cmodel.base.CModel.c_endian_type] and [`c_size_type`][cmodel.base.CModel.c_size_type] control byte order and data type sizes
    when the struct is packed or unpacked.

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

By default, [`c_endian_type`][cmodel.base.CModel.c_endian_type] is `"native"` and
[`c_size_type`][cmodel.base.CModel.c_size_type] is `"native"`, which together select the
native byte order with native data type sizes. Byte order affects how multi-byte fields
are encoded, but it does not change where padding bytes appear.

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

To make the comparison stable across machines, define both models with explicit byte
order and standard sizes:

```python
from io import BytesIO


class LEMixed(CModel, c_endian_type="little", c_size_type="standard"):
    count: Int
    flag: Bool
    value: Float


class LEPackedMixed(CModel, c_alignment=1, c_endian_type="little", c_size_type="standard"):
    count: Int
    flag: Bool
    value: Float


aligned = BytesIO()
LEMixed(count=5, flag=True, value=1.5).c_pack(aligned)

packed = BytesIO()
LEPackedMixed(count=5, flag=True, value=1.5).c_pack(packed)

assert aligned.getvalue() != packed.getvalue()
```

When you are integrating with an existing binary protocol, this kind of comparison is a
good first check.

## Choose byte order separately from alignment

Set [`c_endian_type`][cmodel.base.CModel.c_endian_type] and [`c_size_type`][cmodel.base.CModel.c_size_type] on the model class when the binary format
requires a specific byte order.

Alignment still comes from the model's layout rules and any
[`c_alignment`][cmodel.base.CModel.c_alignment] value on the struct.

```python
class BEPackedMixed(CModel, c_alignment=1, c_endian_type="big", c_size_type="standard"):
    count: Int
    flag: Bool
    value: Float


buf = BytesIO()

BEPackedMixed(count=5, flag=True, value=1.5).c_pack(buf)

buf.seek(0)
decoded = BEPackedMixed.c_unpack(buf)

assert decoded == BEPackedMixed(count=5, flag=True, value=1.5)
```

The important distinction is:

- [`c_alignment`][cmodel.base.CModel.c_alignment] set to `1` changes the layout by removing padding between fields.
- [`c_endian_type`][cmodel.base.CModel.c_endian_type] set to `"big"` changes the byte order of multi-byte values but not the alignment.
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

Byte order is set on each struct independently, just like alignment:

```python
class LEHeader(CModel, c_alignment=1, c_endian_type="little", c_size_type="standard"):
    kind: Int
    length: Int


class LEPayload(CModel, c_endian_type="little", c_size_type="standard"):
    value: Float
    ready: Bool


class LEPacket(CModel, c_endian_type="little", c_size_type="standard"):
    header: LEHeader
    payload: LEPayload


buf = BytesIO()
LEPacket(
    header=LEHeader(kind=1, length=8),
    payload=LEPayload(value=1.5, ready=True),
).c_pack(buf)
```

## Keep the model close to the source layout

If you already have a C declaration, mirror its field order exactly and decide on
alignment immediately. Do not treat padding as an afterthought.

Then decide which byte order and size the protocol uses and set
[`c_endian_type`][cmodel.base.CModel.c_endian_type] and [`c_size_type`][cmodel.base.CModel.c_size_type] on the model class.

Use this guide when you know the bytes you need to match. If the missing piece is an
unusual field encoding rather than padding, continue to
[Define custom field formats](define-custom-field-formats.md).
