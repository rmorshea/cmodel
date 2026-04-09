# Overview

### [Model common structs](model-common-structs.md)

Start here for the everyday building blocks of a CModel definition. This guide covers
scalar fields, nested models, fixed-size repeated values, and fixed-length byte
strings, then shows how to round-trip a model through bytes to confirm the layout.

Read this page first if you are still translating a C struct into Python and want a
practical baseline before worrying about alignment details.

### [Control alignment and layout](control-alignment-and-layout.md)

Use this guide when field order alone is not enough and the exact byte layout matters.
It explains how [`c_alignment`][cmodel.base.CModel.c_alignment] affects padding,
how packed structs differ from aligned structs, and how byte order remains a separate
decision made at pack and unpack time.

Read this page when you are matching an existing binary protocol, file format, or ABI
boundary and need confidence that the bytes land in the right positions.

### [Model tagged unions](model-tagged-unions.md)

Use this guide when a binary protocol or file format sends one of several possible
message layouts, identified by a shared tag field. It shows how to define variant
models, combine them with a Pydantic discriminator, and pack or unpack the correct
variant automatically.

Read this page when the wire format includes a type tag that determines which struct
layout follows.

### [Define custom field formats](define-custom-field-formats.md)

Use this guide when the built-in aliases from [`cmodel.types`][cmodel.types] do not
fully describe a field. It shows how to define a [`CFormat`][cmodel.base.CFormat], adapt raw
binary values into richer Python values, and keep custom formats reusable without
blurring the boundary between field format and struct layout.

Read this page when the structure is straightforward but one or two fields need a more
specialized binary representation.

### [Handle raw bytes fields](handle-raw-bytes-fields.md)

Use this guide when a field cannot be described by a `struct` format string at all.
It shows how to use [`CRaw`][cmodel.base.CRaw] to read and write raw bytes directly,
adapt them to richer Python types, and handle variable-length trailing fields.

Read this page when a field is an opaque blob, uses a custom encoding, or consumes
the rest of the buffer.

## Reading path

- New to CModel: read these guides in order.
- Working from an existing C declaration: start with [Model common structs](model-common-structs.md), then jump to [Control alignment and layout](control-alignment-and-layout.md).
- Working with a type-tagged protocol: go to [Model tagged unions](model-tagged-unions.md).
- Working with unusual field encodings: go straight to [Define custom field formats](define-custom-field-formats.md).
- Working with opaque blobs or custom byte encodings: go to [Handle raw bytes fields](handle-raw-bytes-fields.md).

If you are new to CModel, read these guides in order. If you already have a C struct or
wire format in hand, jump directly to the guide that matches the layout problem you are
solving.
