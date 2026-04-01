import struct
from io import BytesIO
from typing import Annotated as An
from uuid import UUID

import pytest

from cmodel.base import CModel
from cmodel.types import Bool
from cmodel.types import Double
from cmodel.types import Float
from cmodel.types import Int
from cmodel.types import Long
from cmodel.types import Short
from cmodel.types import SignedChar
from cmodel.types import UnsignedChar
from cmodel.types import UnsignedInt
from cmodel.types import UnsignedLong
from cmodel.types import UnsignedShort
from cmodel.types import Uuid
from cmodel.types import c_bool
from cmodel.types import c_char
from cmodel.types import c_double
from cmodel.types import c_float
from cmodel.types import c_int


class _SignedCharModel(CModel):
    field: SignedChar


class _UnsignedCharModel(CModel):
    field: UnsignedChar


class _BoolModel(CModel):
    field: Bool


class _ShortModel(CModel):
    field: Short


class _UnsignedShortModel(CModel):
    field: UnsignedShort


class _IntModel(CModel):
    field: Int


class _UnsignedIntModel(CModel):
    field: UnsignedInt


class _LongModel(CModel):
    field: Long


class _UnsignedLongModel(CModel):
    field: UnsignedLong


class _FloatModel(CModel):
    field: Float


class _DoubleModel(CModel):
    field: Double


@pytest.mark.parametrize(
    ("model_cls", "fmt_char", "value"),
    [
        (_SignedCharModel, "b", 42),
        (_SignedCharModel, "b", -42),
        (_UnsignedCharModel, "B", 200),
        (_BoolModel, "?", True),
        (_BoolModel, "?", False),
        (_ShortModel, "h", 1000),
        (_ShortModel, "h", -1000),
        (_UnsignedShortModel, "H", 65000),
        (_IntModel, "i", 100_000),
        (_IntModel, "i", -100_000),
        (_UnsignedIntModel, "I", 100_000),
        (_LongModel, "l", 100_000),
        (_UnsignedLongModel, "L", 100_000),
        (_FloatModel, "f", 1.5),
        (_DoubleModel, "d", 1.5),
    ],
)
def test_scalar_unpack(model_cls, fmt_char, value):
    buf = BytesIO(struct.pack(fmt_char, value))
    result = model_cls.c_unpack(buf)
    assert result.field == value


@pytest.mark.parametrize(
    ("model_cls", "fmt_char", "value"),
    [
        (_SignedCharModel, "b", 42),
        (_UnsignedCharModel, "B", 200),
        (_BoolModel, "?", True),
        (_ShortModel, "h", -1000),
        (_UnsignedShortModel, "H", 65000),
        (_IntModel, "i", 100_000),
        (_UnsignedIntModel, "I", 100_000),
        (_LongModel, "l", 100_000),
        (_UnsignedLongModel, "L", 100_000),
        (_FloatModel, "f", 1.5),
        (_DoubleModel, "d", 1.5),
    ],
)
def test_scalar_pack(model_cls, fmt_char, value):
    buf = BytesIO()
    model_cls(field=value).c_pack(buf)
    assert buf.getvalue() == struct.pack(fmt_char, value)


class _IntPairModel(CModel):
    field: An[tuple[int, int], c_int(2)]


class _BoolTripleModel(CModel):
    field: An[tuple[bool, bool, bool], c_bool(3)]


class _FloatPairModel(CModel):
    field: An[tuple[float, float], c_float(2)]


class _DoublePairModel(CModel):
    field: An[tuple[float, float], c_double(2)]


@pytest.mark.parametrize(
    ("model_cls", "fmt", "values"),
    [
        (_IntPairModel, "ii", (1, 2)),
        (_BoolTripleModel, "???", (True, False, True)),
        (_FloatPairModel, "ff", (1.5, 2.5)),
        (_DoublePairModel, "dd", (1.5, 2.5)),
    ],
)
def test_multi_count_unpack(model_cls, fmt, values):
    buf = BytesIO(struct.pack(fmt, *values))
    result = model_cls.c_unpack(buf)
    assert result.field == values


@pytest.mark.parametrize(
    ("model_cls", "fmt", "values"),
    [
        (_IntPairModel, "ii", (1, 2)),
        (_BoolTripleModel, "???", (True, False, True)),
        (_FloatPairModel, "ff", (1.5, 2.5)),
        (_DoublePairModel, "dd", (1.5, 2.5)),
    ],
)
def test_multi_count_pack(model_cls, fmt, values):
    buf = BytesIO()
    model_cls(field=values).c_pack(buf)
    assert buf.getvalue() == struct.pack(fmt, *values)


class _CharModel(CModel):
    data: An[bytes, c_char(4)]


def test_c_char_unpack():
    buf = BytesIO(struct.pack("4s", b"test"))
    result = _CharModel.c_unpack(buf)
    assert result.data == b"test"


def test_c_char_pack():
    buf = BytesIO()
    _CharModel(data=b"test").c_pack(buf)
    assert buf.getvalue() == struct.pack("4s", b"test")


def test_c_char_roundtrip():
    original = _CharModel(data=b"test")
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert _CharModel.c_unpack(buf) == original


class _UuidModel(CModel):
    id: Uuid


@pytest.fixture
def sample_uuid():
    return UUID("12345678-1234-5678-1234-567812345678")


def test_uuid_unpack(sample_uuid):
    buf = BytesIO(struct.pack("16s", sample_uuid.bytes))
    result = _UuidModel.c_unpack(buf)
    assert result.id == sample_uuid


def test_uuid_pack(sample_uuid):
    buf = BytesIO()
    _UuidModel(id=sample_uuid).c_pack(buf)
    assert buf.getvalue() == struct.pack("16s", sample_uuid.bytes)


def test_uuid_roundtrip(sample_uuid):
    original = _UuidModel(id=sample_uuid)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert _UuidModel.c_unpack(buf) == original
