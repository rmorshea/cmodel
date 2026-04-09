# How CModel maps Python models to C layouts

CModel combines two concerns that are usually kept apart:

- Python-side data validation
- binary layout for C-compatible data

That combination is the reason the API feels small. The model class is doing both jobs.

## A CModel is still a Pydantic model

[`CModel`][cmodel.base.CModel] subclasses are normal Pydantic models first. Field validation, nested models,
and model construction all happen in the usual Pydantic way.

The binary behavior is added by inspecting the Pydantic core schema and deriving a C
layout from it.

That has two important consequences:

1. You describe your data with Python types, not by manually building a binary schema.
1. The binary layout only exists for shapes that CModel knows how to map from the
    Pydantic schema.

## Field metadata defines the wire format

When you use aliases from [`cmodel.types`][cmodel.types], or an explicit [`CFormat`][cmodel.base.CFormat], you are attaching
binary format metadata to an otherwise ordinary Python type.

For example, `Int` means “validate this as an integer, but pack it with the `i` struct
format”. `Annotated[tuple[int, int, int], c_int(3)]` means “validate this as a tuple of
three integers, and pack it as three consecutive `int` values”.

This split is why the models stay readable. Python types communicate intent. Format
metadata communicates layout.

[`CFormat`][cmodel.base.CFormat] is intentionally limited to one underlying data type per field format string.
Formats such as `BBB` are fine, but mixed-type formats such as `Bh` are not. When one
logical value needs mixed field types, represent it as a tuple or nested model instead.

When a field cannot be expressed as a `struct` format string at all, use
[`CBytes`][cmodel.base.CBytes] instead. [`CBytes`][cmodel.base.CBytes] takes a fixed byte
count (or `None` for variable-length), an alignment, and `validate` / `dump` callables
that convert between raw bytes and the Python value. This is useful for opaque blobs,
custom encodings, or trailing payloads that consume the rest of the buffer.

## Nested models become nested structs

Nested [`CModel`][cmodel.base.CModel] subclasses map directly onto nested C structs. That is not just a
convenience for code organization; it is how layout structure is preserved.

If your source layout has a nested header and payload, model them as separate classes.
The resulting documentation and generated reference will reflect that structure too.

## Tagged unions select a variant by a tag field

When a field is annotated as a union of [`CModel`][cmodel.base.CModel] subclasses with a Pydantic
`Discriminator`, CModel treats it as a tagged union. On unpack, the tag field is read
first to determine which variant layout to use. The selected variant is then unpacked
from the beginning, and surrounding fields continue from where the variant ends.

All variants must share the same tag field name and format. The tag field uses a
`Literal` type to pin each variant to one or more values. This mirrors the C pattern of
a union inside a struct where one member indicates which union field is active.

## Alignment is a struct-level decision

[`CFormat`][cmodel.base.CFormat] describes a field. [`c_alignment`][cmodel.base.CModel.c_alignment] describes how a struct is laid out.

By default, [`CModel`][cmodel.base.CModel] computes a struct alignment from the fields it contains. When you
set [`c_alignment`][cmodel.base.CModel.c_alignment] to `1`, you are saying that this struct should be packed with no alignment
padding.

This separation matters because layout bugs often come from conflating field format with
struct packing. A field can still be an `Int`; what changes is where the next field is
allowed to begin.

## Byte order and data type sizes are set at class definition time

The byte order and data type sizes of a struct are determined by
[`c_endian_type`][cmodel.base.CModel.c_endian_type] and [`c_size_type`][cmodel.base.CModel.c_size_type],
which are set as keyword arguments on the class definition. These two values are combined
into a `struct` format prefix that is baked into the schema when the class is created.
This means the binary layout of a model is fully determined by its class definition, not
by arguments passed at pack or unpack time.

## CModel prefers explicitness over ABI magic

CModel is good at describing fixed layouts that you can reason about directly. It is not
trying to infer every compiler- and platform-specific ABI rule for you.

That tradeoff is useful:

- models stay small and inspectable
- the binary contract lives next to the Python type definition
- mismatches are easier to spot in tests

If you need confidence in a layout, round-trip representative bytes in tests. That is a
better fit for this library than hoping the implementation guessed the same rules as a
specific compiler.
