# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

...

## v0.6.0

- Changed `CEncoderSchema` pack and unpack functions to accept a context arg. In particular, `unpack` now receives a `CUnpackContext` that includes a `preceding_fields` dict for reading previously unpacked fields from the same struct. ([#10](https://github.com/rmorshea/cmodel/pull/10))
- Added `get_c_format_prefix` utility as a public function. ([#10](https://github.com/rmorshea/cmodel/pull/10))

## v0.5.0

- Added support for fields with default values. ([#9](https://github.com/rmorshea/cmodel/pull/9))
- Added built-in types `LongLong`, `UnsignedLongLong`, `SSizeT`, and `SizeT` (format chars `q`, `Q`, `n`, `N`). ([#9](https://github.com/rmorshea/cmodel/pull/9))
- Allowed tagged union schemas to mix variable-length and fixed-length variants. ([#9](https://github.com/rmorshea/cmodel/pull/9))

## v0.4.0

- Added `CEncoded` annotation for fields that need custom or variable-length binary encoding not expressible as a `struct` format string. ([#8](https://github.com/rmorshea/cmodel/pull/8))
- Added `RawBytes` type for trailing variable-length byte fields. ([#8](https://github.com/rmorshea/cmodel/pull/8))
- Fixed inter-field padding to align based on the next field's natural alignment instead of only the struct's overall alignment. ([#8](https://github.com/rmorshea/cmodel/pull/8))
- Changed internal schema representation from `CFormatSchema` to `CEncoderSchema`. `CFormat` fields are now converted to `CEncoderSchema` internally. ([#8](https://github.com/rmorshea/cmodel/pull/8))

## v0.3.0

- Changed handling of endians. Byte order and data type sizes are now set at class definition time with `c_endian_type` and `c_size_type`, instead of being passed as arguments to `c_pack` and `c_unpack`. This means the binary layout of a model is fully determined by its class definition, not by arguments passed at pack or unpack time. ([#6](https://github.com/rmorshea/cmodel/pull/6))

## v0.2.0

- Added support for Pydantic tagged unions ([#5](https://github.com/rmorshea/cmodel/pull/5))

## v0.1.0

Initial release with all basic functionality:

- Added `CModel` base class
- Added `CFormat` for custom field formats
- Added built-in field types in `cmodel.types`
- Added guides and documentation
