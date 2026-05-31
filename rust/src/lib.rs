use pyo3::exceptions::{PyKeyError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyDict, PyModule, PyTuple};

fn missing_key(key: &str) -> PyErr {
    PyKeyError::new_err(key.to_string())
}

fn dict_item<'py>(obj: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    let dict = obj.cast::<PyDict>()?;
    dict.get_item(key)?.ok_or_else(|| missing_key(key))
}

fn dict_string(obj: &Bound<'_, PyAny>, key: &str) -> PyResult<String> {
    dict_item(obj, key)?.extract()
}

fn dict_usize(obj: &Bound<'_, PyAny>, key: &str) -> PyResult<usize> {
    dict_item(obj, key)?.extract()
}

fn make_pack_context<'py>(
    py: Python<'py>,
    struct_schema: &Bound<'py, PyAny>,
    field_name: &str,
) -> PyResult<Bound<'py, PyDict>> {
    let context = PyDict::new(py);
    context.set_item("struct_schema", struct_schema)?;
    context.set_item("field_name", field_name)?;
    Ok(context)
}

fn make_unpack_context<'py>(
    py: Python<'py>,
    struct_schema: &Bound<'py, PyAny>,
    field_name: &str,
    preceding_fields: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let context = PyDict::new(py);
    context.set_item("struct_schema", struct_schema)?;
    context.set_item("field_name", field_name)?;
    context.set_item("preceding_fields", preceding_fields)?;
    Ok(context)
}

fn placeholder_struct_schema(py: Python<'_>, anonymous: bool) -> PyResult<Bound<'_, PyDict>> {
    let schema = PyDict::new(py);
    schema.set_item("type", "struct")?;
    schema.set_item("field_schemas", PyDict::new(py))?;
    schema.set_item("alignment", 0)?;
    schema.set_item("endian_type", "native")?;
    schema.set_item("size_type", "native")?;
    schema.set_item("anonymous", anonymous)?;
    Ok(schema)
}

fn io_tell(io: &Bound<'_, PyAny>) -> PyResult<usize> {
    io.call_method0("tell")?.extract()
}

fn io_seek(io: &Bound<'_, PyAny>, offset: isize, whence: i32) -> PyResult<()> {
    io.call_method1("seek", (offset, whence))?;
    Ok(())
}

fn io_buffer_len(io: &Bound<'_, PyAny>) -> PyResult<usize> {
    io.call_method0("getbuffer")?.len()
}

fn io_write_padding(py: Python<'_>, io: &Bound<'_, PyAny>, padding: usize) -> PyResult<()> {
    if padding == 0 {
        return Ok(());
    }
    io.call_method1("write", (PyBytes::new(py, &vec![0; padding]),))?;
    Ok(())
}

fn next_padding(
    idx: usize,
    position: usize,
    field_schemas: &[Py<PyAny>],
    struct_align: usize,
) -> PyResult<usize> {
    let next_align = Python::attach(|py| -> PyResult<usize> {
        if idx + 1 < field_schemas.len() {
            let next_schema = field_schemas[idx + 1].bind(py);
            let next_schema = dict_item(next_schema, "schema")?;
            let next_align = dict_usize(&next_schema, "alignment")?;
            Ok(next_align.min(struct_align))
        } else {
            Ok(struct_align)
        }
    })?;
    if next_align == 0 {
        return Ok(0);
    }
    Ok((next_align - (position % next_align)) % next_align)
}

fn dict_values_in_order(dict: &Bound<'_, PyDict>) -> Vec<Py<PyAny>> {
    dict.iter().map(|(_, value)| value.unbind()).collect()
}

fn variant_schema_for<'py>(
    mapping: &Bound<'py, PyAny>,
    key: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let maybe_schema = mapping.call_method1("get", (key,))?;
    if maybe_schema.is_none() {
        Ok(None)
    } else {
        Ok(Some(maybe_schema))
    }
}

fn unpack_impl<'py>(
    py: Python<'py>,
    io: &Bound<'py, PyAny>,
    schema: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<Py<PyAny>> {
    match dict_string(schema, "type")?.as_str() {
        "encoder" => Ok(dict_item(schema, "unpack")?.call1((io, context))?.unbind()),
        "struct" => {
            let alignment = dict_usize(schema, "alignment")?;
            let field_schemas_obj = dict_item(schema, "field_schemas")?;
            let field_schemas = field_schemas_obj.cast::<PyDict>()?;
            let field_list = dict_values_in_order(&field_schemas);
            let anonymous: bool = dict_item(schema, "anonymous")?.extract()?;

            if anonymous {
                let preceding_fields = PyDict::new(py);
                let struct_context = make_unpack_context(py, schema, "", &preceding_fields)?;
                let mut tuple_values = Vec::with_capacity(field_list.len());
                for (idx, field_schema) in field_list.iter().enumerate() {
                    let field_schema = field_schema.bind(py);
                    let nested_schema = dict_item(field_schema, "schema")?;
                    tuple_values.push(unpack_impl(py, io, &nested_schema, struct_context.as_any())?);
                    let padding = next_padding(idx, io_tell(io)?, &field_list, alignment)?;
                    io_seek(io, padding as isize, 1)?;
                }
                Ok(PyTuple::new(py, tuple_values)?.into_any().unbind())
            } else {
                let dict_values = PyDict::new(py);
                for (idx, (field_name, field_schema)) in field_schemas.iter().enumerate() {
                    let field_name: String = field_name.extract()?;
                    let field_context =
                        make_unpack_context(py, schema, &field_name, &dict_values)?;
                    let nested_schema = dict_item(&field_schema, "schema")?;
                    let unpacked = unpack_impl(py, io, &nested_schema, field_context.as_any())?;
                    dict_values.set_item(&field_name, unpacked)?;
                    let padding = next_padding(idx, io_tell(io)?, &field_list, alignment)?;
                    io_seek(io, padding as isize, 1)?;
                }
                Ok(dict_values.into_any().unbind())
            }
        }
        "tagged-union" => {
            let tag_schema = dict_item(schema, "tag_schema")?;
            let tag_size_obj = dict_item(&tag_schema, "size")?;
            if tag_size_obj.is_none() {
                return Err(PyValueError::new_err(
                    "Tag schema for tagged union must have a fixed size",
                ));
            }
            let tag_size: usize = tag_size_obj.extract()?;
            let tag_value = unpack_impl(py, io, &tag_schema, context)?;
            io_seek(io, -(tag_size as isize), 0)?;
            let variant_schemas = dict_item(schema, "variant_schemas")?;
            let Some(variant_schema) = variant_schema_for(&variant_schemas, tag_value.bind(py))? else {
                return Err(PyValueError::new_err(format!(
                    "Invalid tag value {} for tagged union",
                    tag_value.bind(py).str()?
                )));
            };
            unpack_impl(py, io, &variant_schema, context)
        }
        "array" => {
            let item_schema = dict_item(schema, "item_schema")?;
            let count_schema = dict_item(schema, "count_schema")?;
            if count_schema.is_none() {
                let mut items = Vec::new();
                while io_tell(io)? < io_buffer_len(io)? {
                    items.push(unpack_impl(py, io, &item_schema, context)?);
                }
                Ok(PyTuple::new(py, items)?.into_any().unbind())
            } else {
                let count_field_name: String = dict_item(&count_schema, "count_field_name")?.extract()?;
                let count_field_as_int = dict_item(&count_schema, "count_field_as_int")?;
                let preceding_fields = dict_item(context, "preceding_fields")?;
                let count_value = preceding_fields.get_item(&count_field_name)?;
                let count: usize = count_field_as_int.call1((count_value,))?.extract()?;
                let mut items = Vec::with_capacity(count);
                for _ in 0..count {
                    items.push(unpack_impl(py, io, &item_schema, context)?);
                }
                Ok(PyTuple::new(py, items)?.into_any().unbind())
            }
        }
        schema_type => Err(PyTypeError::new_err(format!(
            "Unsupported schema type: {schema_type}"
        ))),
    }
}

fn pack_impl<'py>(
    py: Python<'py>,
    io: &Bound<'py, PyAny>,
    schema: &Bound<'py, PyAny>,
    value: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<()> {
    match dict_string(schema, "type")?.as_str() {
        "encoder" => {
            dict_item(schema, "pack")?.call1((io, value, context))?;
            Ok(())
        }
        "struct" => {
            let alignment = dict_usize(schema, "alignment")?;
            let field_schemas_obj = dict_item(schema, "field_schemas")?;
            let field_schemas = field_schemas_obj.cast::<PyDict>()?;
            let field_list = dict_values_in_order(&field_schemas);
            let anonymous: bool = dict_item(schema, "anonymous")?.extract()?;

            if anonymous {
                let values = value.try_iter()?;
                let values: Vec<_> = values.collect::<PyResult<Vec<_>>>()?;
                if values.len() != field_list.len() {
                    return Err(PyValueError::new_err(
                        "Anonymous struct value length does not match schema fields",
                    ));
                }
                for (idx, (field_schema, item_value)) in field_list.iter().zip(values).enumerate() {
                    let field_schema = field_schema.bind(py);
                    let nested_schema = dict_item(field_schema, "schema")?;
                    let field_context = make_pack_context(py, schema, "")?;
                    pack_impl(py, io, &nested_schema, &item_value, field_context.as_any())?;
                    let padding = next_padding(idx, io_tell(io)?, &field_list, alignment)?;
                    io_write_padding(py, io, padding)?;
                }
                Ok(())
            } else {
                for (idx, (field_name, field_schema)) in field_schemas.iter().enumerate() {
                    let field_name: String = field_name.extract()?;
                    let field_context = make_pack_context(py, schema, &field_name)?;
                    let nested_schema = dict_item(&field_schema, "schema")?;
                    let item_value = value.get_item(&field_name)?;
                    pack_impl(py, io, &nested_schema, &item_value, field_context.as_any())?;
                    let padding = next_padding(idx, io_tell(io)?, &field_list, alignment)?;
                    io_write_padding(py, io, padding)?;
                }
                Ok(())
            }
        }
        "tagged-union" => {
            let tag_field: String = dict_item(schema, "tag_field")?.extract()?;
            let tag_value = value.get_item(&tag_field)?;
            let variant_schemas = dict_item(schema, "variant_schemas")?;
            let Some(variant_schema) = variant_schema_for(&variant_schemas, &tag_value)? else {
                return Err(PyValueError::new_err(format!(
                    "Invalid tag value {} for tagged union",
                    tag_value.str()?
                )));
            };
            pack_impl(py, io, &variant_schema, value, context)
        }
        "array" => {
            let item_schema = dict_item(schema, "item_schema")?;
            for item in value.try_iter()? {
                let item = item?;
                pack_impl(py, io, &item_schema, &item, context)?;
            }
            Ok(())
        }
        schema_type => Err(PyTypeError::new_err(format!(
            "Unsupported schema type: {schema_type}"
        ))),
    }
}

#[pyfunction]
fn unpack_c_schema(py: Python<'_>, io: Py<PyAny>, schema: Py<PyAny>) -> PyResult<Py<PyAny>> {
    let placeholder = placeholder_struct_schema(py, true)?;
    let preceding_fields = PyDict::new(py);
    let context = make_unpack_context(py, placeholder.as_any(), "", &preceding_fields)?;
    unpack_impl(py, io.bind(py), schema.bind(py), context.as_any())
}

#[pyfunction]
fn pack_c_schema(py: Python<'_>, io: Py<PyAny>, schema: Py<PyAny>, value: Py<PyAny>) -> PyResult<()> {
    let placeholder = placeholder_struct_schema(py, true)?;
    let context = make_pack_context(py, placeholder.as_any(), "")?;
    pack_impl(py, io.bind(py), schema.bind(py), value.bind(py), context.as_any())
}

#[pymodule(name = "_lib")]
fn _lib(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(unpack_c_schema, module)?)?;
    module.add_function(wrap_pyfunction!(pack_c_schema, module)?)?;
    Ok(())
}
