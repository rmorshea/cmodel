import struct
from io import BytesIO
from typing import Annotated as An

import pytest
from pydantic import BaseModel

from cmodel.base import CModel
from cmodel.types import Bool
from cmodel.types import Float
from cmodel.types import Int
from cmodel.types import c_int


class PointModel(CModel):
    x: Int
    y: Int


class LineModel(CModel):
    start: PointModel
    end: PointModel


class MixedModel(CModel):
    count: Int
    flag: Bool
    value: Float


class TupleModel(CModel):
    coords: An[tuple[int, int, int], c_int(3)]


@pytest.fixture
def point_model():
    return PointModel(x=3, y=7)


@pytest.fixture
def point_buf():
    return BytesIO(struct.pack("ii", 3, 7))


def test_unpack_reads_fields_in_order(point_buf):
    result = PointModel.c_unpack(point_buf)
    assert result.x == 3
    assert result.y == 7


def test_pack_writes_fields_in_order(point_model):
    buf = BytesIO()
    point_model.c_pack(buf)
    assert buf.getvalue() == struct.pack("ii", 3, 7)


@pytest.mark.parametrize(("x", "y"), [(0, 0), (1, -1), (2**30, -(2**30))])
def test_roundtrip(x, y):
    model = PointModel(x=x, y=y)
    buf = BytesIO()
    model.c_pack(buf)
    buf.seek(0)
    assert PointModel.c_unpack(buf) == model


def test_model_validates_normally():
    point = PointModel(x=1, y=2)
    assert point.x == 1
    assert point.y == 2


def test_mixed_model_unpack():
    buf = BytesIO(struct.pack("i", 5) + struct.pack("?", True) + struct.pack("f", 1.5))
    result = MixedModel.c_unpack(buf)
    assert result.count == 5
    assert result.flag is True
    assert result.value == pytest.approx(1.5)


def test_mixed_model_pack():
    model = MixedModel(count=5, flag=True, value=1.5)
    buf = BytesIO()
    model.c_pack(buf)
    assert buf.getvalue() == struct.pack("i", 5) + struct.pack("?", True) + struct.pack("f", 1.5)


def test_nested_unpack():
    buf = BytesIO(struct.pack("iiii", 1, 2, 3, 4))
    result = LineModel.c_unpack(buf)
    assert result.start == PointModel(x=1, y=2)
    assert result.end == PointModel(x=3, y=4)


def test_nested_pack():
    model = LineModel(start=PointModel(x=1, y=2), end=PointModel(x=3, y=4))
    buf = BytesIO()
    model.c_pack(buf)
    assert buf.getvalue() == struct.pack("iiii", 1, 2, 3, 4)


def test_nested_roundtrip():
    original = LineModel(start=PointModel(x=1, y=2), end=PointModel(x=3, y=4))
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert LineModel.c_unpack(buf) == original


def test_tuple_field_unpack():
    buf = BytesIO(struct.pack("iii", 10, 20, 30))
    result = TupleModel.c_unpack(buf)
    assert result.coords == (10, 20, 30)


def test_tuple_field_pack():
    buf = BytesIO()
    TupleModel(coords=(10, 20, 30)).c_pack(buf)
    assert buf.getvalue() == struct.pack("iii", 10, 20, 30)


def test_tuple_field_roundtrip():
    original = TupleModel(coords=(10, 20, 30))
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert TupleModel.c_unpack(buf) == original


def test_variadic_tuple_not_supported():
    with pytest.raises(ValueError, match="variadic"):

        class BadModel(CModel):
            values: tuple[int, ...]


def test_non_cmodel_nested_not_supported():
    class PlainModel(BaseModel):
        value: int

    with pytest.raises(TypeError, match="CModel"):

        class BadModel(CModel):
            nested: PlainModel


def test_unsupported_schema_type_raises():
    with pytest.raises(TypeError, match="Unsupported schema type"):

        class BadModel(CModel):
            value: int  # bare int without CFmt annotation
