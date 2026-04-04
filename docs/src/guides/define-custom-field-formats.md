# Define custom field formats

Use `CFmt` when the built-in aliases in `cmodel.types` do not describe the field you
need. `CFmt` lets you define:

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

`CFmt` format strings do not accept byte-order or alignment prefixes such as `@`, `=`,
`<`, `>`, or `!`. CModel treats field layout and struct alignment as separate concerns.

That means:

- use the field format to describe the field itself
- use `c_alignment` on the model to describe struct packing behavior

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

`CFmt` is the escape hatch, not the default. Reach for `cmodel.types` first, then use
custom formats only where they make the binary contract clearer.
