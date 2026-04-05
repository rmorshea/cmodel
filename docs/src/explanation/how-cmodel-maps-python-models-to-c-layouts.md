# How CModel maps Python models to C layouts

CModel combines two concerns that are usually kept apart:

- Python-side data validation
- binary layout for C-compatible data

That combination is the reason the API feels small. The model class is doing both jobs.

## A CModel is still a Pydantic model

`CModel` subclasses are normal Pydantic models first. Field validation, nested models,
and model construction all happen in the usual Pydantic way.

The binary behavior is added by inspecting the Pydantic core schema and deriving a C
layout from it.

That has two important consequences:

1. You describe your data with Python types, not by manually building a binary schema.
1. The binary layout only exists for shapes that CModel knows how to map from the
    Pydantic schema.

## Field metadata defines the wire format

When you use aliases from `cmodel.types`, or an explicit `CFmt`, you are attaching
binary format metadata to an otherwise ordinary Python type.

For example, `Int` means “validate this as an integer, but pack it with the `i` struct
format”. `Annotated[tuple[int, int, int], c_int(3)]` means “validate this as a tuple of
three integers, and pack it as three consecutive `int` values”.

This split is why the models stay readable. Python types communicate intent. Format
metadata communicates layout.

## Nested models become nested structs

Nested `CModel` subclasses map directly onto nested C structs. That is not just a
convenience for code organization; it is how layout structure is preserved.

If your source layout has a nested header and payload, model them as separate classes.
The resulting documentation and generated reference will reflect that structure too.

## Alignment is a struct-level decision

`CFmt` describes a field. `c_alignment` describes how a struct is laid out.

By default, CModel computes a struct alignment from the fields it contains. When you
set `c_alignment=1`, you are saying that this struct should be packed with no alignment
padding.

This separation matters because layout bugs often come from conflating field format with
struct packing. A field can still be an `Int`; what changes is where the next field is
allowed to begin.

## Byte order is determined at runtime

The byte order of the data being packed or unpacked by a struct is determined by an
`endian` argument passed to `CModel.c_pack` or `CModel.c_unpack`

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
