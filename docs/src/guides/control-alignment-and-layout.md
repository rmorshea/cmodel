# Control alignment and layout

The fastest way to get incorrect binary data is to assume the layout has no padding.
CModel lets you keep the default aligned behavior, or opt into packed layouts when the
target format requires it.

## Understand the default

By default, CModel derives a struct alignment from the fields in the model. That means
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

## Use packed layout when the bytes are contiguous

Set `c_alignment=1` on the model class when the target binary format is packed.

```python
class PackedMixed(CModel, c_alignment=1):
    count: Int
    flag: Bool
    value: Float
```

Now CModel writes each field immediately after the previous one with no alignment
padding inserted.

## Compare the two layouts

```python
from io import BytesIO


aligned = BytesIO()
Mixed(count=5, flag=True, value=1.5).c_pack(aligned)

packed = BytesIO()
PackedMixed(count=5, flag=True, value=1.5).c_pack(packed)

assert aligned.getvalue() != packed.getvalue()
```

When you are integrating with an existing binary protocol, this kind of comparison is a
good first check.

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

## Keep the model close to the source layout

If you already have a C declaration, mirror its field order exactly and decide on
alignment immediately. Do not treat padding as an afterthought.

Use this guide when you know the bytes you need to match. If the missing piece is an
unusual field encoding rather than padding, continue to
[Define custom field formats](define-custom-field-formats.md).
