# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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
