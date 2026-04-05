# Define custom field formats

Use [`CFmt`][cmodel.base.CFmt] when the built-in aliases in [`cmodel.types`][cmodel.types] do not describe the field you
need. [`CFmt`][cmodel.base.CFmt] lets you define:

- the underlying `struct` format string
- how unpacked values become Python objects
- how Python objects are turned back into raw values for packing

## Start with the simplest possible format

If the raw binary value already matches the Python value you want, you only need the
format string.

```python
from typing import Annotated

from cmodel import CFmt
from cmodel import CModel

RGB = Annotated[tuple[int, int, int], CFmt("BBB")]


class Pixel(CModel):
    color: RGB
```

That field packs three unsigned bytes and unpacks them as a tuple of three integers.

## Adapt the raw bytes to a richer Python type

Use `validate` and `dump` when the Python representation should differ from the raw
binary representation.

```python
from typing import Annotated

from cmodel import CFmt
from cmodel import CModel

MacAddress = Annotated[
    str,
    CFmt(
        "6B",
        validate=lambda parts: ":".join(f"{part:02x}" for part in parts),
        dump=lambda value: tuple(int(part, 16) for part in value.split(":")),
    ),
]


class Device(CModel):
    address: MacAddress
```

After unpacking, `address` is a string such as `"aa:bb:cc:dd:ee:ff"`. Before packing,
the string is converted back into six unsigned bytes.

## Keep format strings field-local

[`CFmt`][cmodel.base.CFmt] format strings do not accept byte-order or alignment prefixes such as `@`, `=`,
`<`, `>`, or `!`. [`CModel`][cmodel.base.CModel] treats field layout and struct alignment as separate concerns.

[`CFmt`][cmodel.base.CFmt] also only supports one data type per format string. Repeated values such as
`BBB` or `3h` are fine, but mixed layouts such as `Bh` or `if` are rejected.

That means:

- use the field format to describe the field itself
- use [`c_alignment`][cmodel.base.CModel.c_alignment] on the model to describe struct packing behavior
- if a logical value needs mixed field types, model it as multiple values, typically a
    tuple or nested [`CModel`][cmodel.base.CModel]

This restriction exists because [`CModel`][cmodel.base.CModel] applies byte order at the field level while
handling struct alignment separately. A mixed-type [`CFmt`][cmodel.base.CFmt] would blur that boundary.

## Use a tuple when one logical value mixes field types

If you need a single logical field that contains mixed C types, represent it as a tuple
or another structured Python value instead of a single `CFmt` string.

```python
from cmodel import CModel
from cmodel.types import Bool
from cmodel.types import Short


class SensorFlags(CModel):
    reading: tuple[Bool, Short]
```

If you want a reusable alias, use a tuple annotation with the existing field helpers:

```python
FlagAndCount = tuple[Bool, Short]


class SensorFlags(CModel):
    reading: FlagAndCount
```

For a richer Python representation, keep the mixed values in a tuple at the binary
boundary and adapt them in your own application code, or split them into a nested model
with named fields.

## Reuse custom formats as aliases

If a custom format appears in more than one place, define it once and reuse it as a
type alias.

```python
Temperature = Annotated[int, CFmt("h")]


class Sample(CModel):
    ambient: Temperature
    surface: Temperature
```

This keeps the model readable and makes layout changes easier to manage.

## Prefer the built-ins when they already fit

[`CFmt`][cmodel.base.CFmt] is the escape hatch, not the default. Reach for [`cmodel.types`][cmodel.types] first, then use
custom formats only where they make the binary contract clearer.
