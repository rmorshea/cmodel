# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Support for variable-length arrays via bare `tuple[T, ...]` fields, which read all remaining bytes in the buffer (must be the last field in a struct). ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `CCountedBy` annotation for variadic tuple fields whose element count is stored in another field. Supports `CCountedBy.name(field_name)` for a static count field name and `CCountedBy.template("{}_count")` for a name derived from the array field name. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `CountedArray[T]` convenience type alias for `tuple[T, ...]` annotated with `CCountedBy.template("{}_count")`, expecting a preceding `{field_name}_count` field. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `SizeRange` enum (`FIXED`, `BOUNDED`, `UNBOUNDED`) to classify whether a field has a fixed, bounded-variable, or unbounded-variable size. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `CBuildContext` TypedDict providing endianness, size type, field name, and struct schema to functions that build C schemas at class-definition time. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `CArraySchema` and `CArrayCountSchema` internal schema types for representing C arrays. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- Support for Pydantic `function-after`, `function-before`, and `function-wrap` validator schemas, which are now transparently handled during schema construction. ([#11](https://github.com/rmorshea/cmodel/pull/11))

### Changed

- `CEncoded.get_encoder` now receives a single `CBuildContext` dict instead of separate `endian_type` and `size_type` positional arguments. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `CEncoderSchema` now requires a `size_range: SizeRange` field. ([#11](https://github.com/rmorshea/cmodel/pull/11))
- `CStructFieldSchema.variable_length: bool` has been replaced by `size_range: SizeRange`. ([#11](https://github.com/rmorshea/cmodel/pull/11))

## v0.6.0

### Added

- `get_c_format_prefix` utility as a public function. ([#10](https://github.com/rmorshea/cmodel/pull/10))

### Changed

- `CEncoderSchema` pack and unpack functions now accept a context arg. In particular, `unpack` now receives a `CUnpackContext` that includes a `preceding_fields` dict for reading previously unpacked fields from the same struct. ([#10](https://github.com/rmorshea/cmodel/pull/10))

## v0.5.0

### Added

- Support for fields with default values. ([#9](https://github.com/rmorshea/cmodel/pull/9))
- Built-in types `LongLong`, `UnsignedLongLong`, `SSizeT`, and `SizeT` (format chars `q`, `Q`, `n`, `N`). ([#9](https://github.com/rmorshea/cmodel/pull/9))
- Tagged union schemas can now mix variable-length and fixed-length variants. ([#9](https://github.com/rmorshea/cmodel/pull/9))

## v0.4.0

### Added

- `CEncoded` annotation for fields that need custom or variable-length binary encoding not expressible as a `struct` format string. ([#8](https://github.com/rmorshea/cmodel/pull/8))
- `RawBytes` type for trailing variable-length byte fields. ([#8](https://github.com/rmorshea/cmodel/pull/8))

### Changed

- Internal schema representation changed from `CFormatSchema` to `CEncoderSchema`. `CFormat` fields are now converted to `CEncoderSchema` internally. ([#8](https://github.com/rmorshea/cmodel/pull/8))

### Fixed

- Inter-field padding now aligns based on the next field's natural alignment instead of only the struct's overall alignment. ([#8](https://github.com/rmorshea/cmodel/pull/8))

## v0.3.0

### Changed

- Byte order and data type sizes are now set at class definition time with `c_endian_type` and `c_size_type`, instead of being passed as arguments to `c_pack` and `c_unpack`. This means the binary layout of a model is fully determined by its class definition, not by arguments passed at pack or unpack time. ([#6](https://github.com/rmorshea/cmodel/pull/6))

## v0.2.0

### Added

- Support for Pydantic tagged unions. ([#5](https://github.com/rmorshea/cmodel/pull/5))

## v0.1.0

### Added

- `CModel` base class.
- `CFormat` for custom field formats.
- Built-in field types in `cmodel.types`.
- Guides and documentation.
