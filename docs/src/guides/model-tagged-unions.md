# Model tagged unions

Use tagged unions when a binary protocol or file format sends one of several possible
message layouts, identified by a shared tag field at the start.

This is the C equivalent of a union inside a struct where one field decides which member
is active. CModel handles this with Pydantic's discriminated union support and the same
field aliases you already use for scalar types.

## Define variant models that share a tag field

Each variant is a separate [`CModel`][cmodel.base.CModel] subclass. They must all include
a tag field with the same name, the same format, and a `Literal` type that pins the
tag to one or more values.

```python
from typing import Annotated, Literal

from cmodel import CModel
from cmodel.types import Bool, Float, Int, UnsignedInt, UnsignedShort, c_char, c_int


class ConnectMessage(CModel):
    msg_type: Annotated[Literal[1], c_int(1)]
    protocol_version: UnsignedShort
    keepalive_seconds: UnsignedShort


class DataMessage(CModel):
    msg_type: Annotated[Literal[2], c_int(1)]
    channel_id: UnsignedInt
    payload_length: UnsignedInt
    payload: Annotated[bytes, c_char(64)]


class DisconnectMessage(CModel):
    msg_type: Annotated[Literal[3], c_int(1)]
    reason_code: UnsignedInt
```

`c_int(1)` is the same format used by `Int`. The explicit form is needed here because
the Python type is `Literal[...]`, not `int`. Every variant must use the same format
for the tag field.

## Combine the variants with a discriminator

Use `typing.Annotated` and Pydantic's `Discriminator` to declare a field that accepts
any of the variants.

```python
from pydantic import Discriminator


class MessageFrame(CModel):
    message: Annotated[
        ConnectMessage | DataMessage | DisconnectMessage,
        Discriminator("msg_type"),
    ]
    sequence_number: UnsignedInt
```

The string passed to `Discriminator` must match the tag field name shared by all
variants.

## Pack and unpack as usual

Tagged unions work with [`c_pack()`][cmodel.base.CModel.c_pack] and
[`c_unpack()`][cmodel.base.CModel.c_unpack] exactly like any other field.

```python
from io import BytesIO


frame = MessageFrame(
    message=DataMessage(msg_type=2, channel_id=5, payload_length=12, payload=b"\x01" * 64),
    sequence_number=42,
)

buf = BytesIO()
frame.c_pack(buf)

buf.seek(0)
decoded = MessageFrame.c_unpack(buf)

assert decoded == frame
assert isinstance(decoded.message, DataMessage)
```

When unpacking, CModel reads the tag field first, selects the matching variant, then
rewinds and unpacks that variant in full. The surrounding struct continues from where
the chosen variant ends.

## Map multiple tag values to one variant

A single variant can accept more than one tag value by listing them in `Literal`.

```python
class ErrorMessage(CModel):
    msg_type: Annotated[Literal[10, 11, 12], c_int(1)]
    error_code: UnsignedInt
    severity: UnsignedShort
```

Here `c_int(1)` appears again because the tag type is `Literal[10, 11, 12]`, not
`int`. The format still matches the other variants.

This is useful when several wire codes share the same layout but carry different
semantic meaning. Each listed value gets its own entry in the discriminator lookup.

## Constraints to keep in mind

**Same tag field format across variants.** Every variant in a union must use the same
format annotation for the tag field. Mixing `c_int(1)` and `c_short(1)` on the
same discriminator field is an error.

**String discriminators only.** The discriminator must be a field name (a string), not
a callable or other Pydantic discriminator form.

**No anonymous variant structs.** Each variant must be a named [`CModel`][cmodel.base.CModel] subclass,
not a bare tuple or anonymous struct.

## When to move on

This guide is enough when your protocol has a fixed set of message shapes identified by
a tag field. If the binary contract also requires packed layouts or a specific byte
order, combine this with the techniques in
[Control alignment and layout](control-alignment-and-layout.md). If a field inside one
of your variants needs a custom binary representation, see
[Define custom field formats](define-custom-field-formats.md).
