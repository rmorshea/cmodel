# Details Overview

The details section explains how CModel turns Pydantic models into binary layouts.

Use these pages when you want the design rationale behind the API rather than a
task-focused walkthrough.

## In this section

### [How CModel maps Python models to C layouts](how-cmodel-maps-python-models-to-c-layouts.md)

This page explains the core translation model behind the library. It covers how
[`CModel`][cmodel.base.CModel] builds on top of Pydantic models, how field metadata
defines binary representation, how nested models become nested structs, and why
alignment is handled as a struct-level concern rather than as part of an individual
field format.

Read this page when you want to understand the constraints behind the public API, why
some format strings are allowed and others are rejected, or how CModel separates Python
validation concerns from binary layout concerns.

## When to use this section

- Use the guides when you are actively implementing a model.
- Use the details pages when you need to understand how the implementation thinks about
    schemas and layouts.
- Use both when you are debugging a layout mismatch and want both the practical steps
    and the design rationale.

If you are trying to model a struct right now, start in [Guides Overview](../guides/index.md)
and come back here when you want to understand why the library behaves the way it does.
