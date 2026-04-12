import struct
from io import BytesIO
from typing import Annotated as An
from typing import Literal

import pytest
from pydantic import Discriminator

from cmodel.base import CModel
from cmodel.types import Bool
from cmodel.types import Float
from cmodel.types import Int
from cmodel.types import c_int
from cmodel.types import c_short


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


class PackedMixedModel(CModel, c_alignment=1):
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
    buf = BytesIO(struct.pack("i?f", 5, True, 1.5))
    result = MixedModel.c_unpack(buf)
    assert result.count == 5
    assert result.flag is True
    assert result.value == pytest.approx(1.5)


def test_mixed_model_pack():
    model = MixedModel(count=5, flag=True, value=1.5)
    buf = BytesIO()
    model.c_pack(buf)
    assert buf.getvalue() == struct.pack("i?f", 5, True, 1.5)


def test_packed_model_unpack_reads_packed_bytes():
    packed_data = struct.pack("i", 5) + struct.pack("?", True) + struct.pack("f", 1.5)
    result = PackedMixedModel.c_unpack(BytesIO(packed_data))
    assert result.count == 5
    assert result.flag is True
    assert result.value == pytest.approx(1.5)


def test_packed_model_pack_uses_c_alignment_1():
    model = PackedMixedModel(count=5, flag=True, value=1.5)
    buf = BytesIO()
    model.c_pack(buf)

    aligned_data = struct.pack("i?f", 5, True, 1.5)
    packed_data = struct.pack("i", 5) + struct.pack("?", True) + struct.pack("f", 1.5)

    assert buf.getvalue() == packed_data
    assert buf.getvalue() != aligned_data


def test_packed_model_roundtrip():
    original = PackedMixedModel(count=5, flag=True, value=1.5)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert PackedMixedModel.c_unpack(buf) == original


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


class _Cat(CModel):
    pet_type: An[Literal[1], c_int(1)]
    meows: Int


class _Dog(CModel):
    pet_type: An[Literal[2], c_int(1)]
    barks: Float
    trained: Bool


class _Lizard(CModel):
    pet_type: An[Literal[3, 4], c_int(1)]
    scales: Bool


class _PetEnvelope(CModel):
    pet: An[_Cat | _Dog | _Lizard, Discriminator("pet_type")]
    n: Int


@pytest.mark.parametrize(
    ("payload", "expected_pet"),
    [
        (struct.pack("iii", 1, 7, 99), _Cat(pet_type=1, meows=7)),
        (struct.pack("if?i", 2, 11.5, True, 42), _Dog(pet_type=2, barks=11.5, trained=True)),
        (struct.pack("i?i", 3, True, 5), _Lizard(pet_type=3, scales=True)),
        (struct.pack("i?i", 4, False, 8), _Lizard(pet_type=4, scales=False)),
    ],
)
def test_tagged_union_unpack_uses_discriminator(payload, expected_pet):
    result = _PetEnvelope.c_unpack(BytesIO(payload))
    assert result.pet == expected_pet


@pytest.mark.parametrize(
    ("pet", "n", "expected"),
    [
        (_Cat(pet_type=1, meows=7), 99, struct.pack("iii", 1, 7, 99)),
        (_Dog(pet_type=2, barks=11.5, trained=True), 42, struct.pack("if?i", 2, 11.5, True, 42)),
        (_Lizard(pet_type=4, scales=False), 8, struct.pack("i?i", 4, False, 8)),
    ],
)
def test_tagged_union_pack_writes_active_variant(pet, n, expected):
    buf = BytesIO()
    _PetEnvelope(pet=pet, n=n).c_pack(buf)
    assert buf.getvalue() == expected


@pytest.mark.parametrize(
    ("pet", "n"),
    [
        (_Cat(pet_type=1, meows=7), 99),
        (_Dog(pet_type=2, barks=11.5, trained=True), 42),
        (_Lizard(pet_type=3, scales=True), 5),
        (_Lizard(pet_type=4, scales=False), 8),
    ],
)
def test_tagged_union_roundtrip(pet, n):
    original = _PetEnvelope(pet=pet, n=n)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert _PetEnvelope.c_unpack(buf) == original


def test_tagged_union_unpack_rejects_unknown_tag():
    with pytest.raises(ValueError, match="Invalid tag value 9"):
        _PetEnvelope.c_unpack(BytesIO(struct.pack("iii", 9, 1, 2)))


def test_tagged_union_requires_matching_tag_field_schema():
    class _ShortTaggedCat(CModel):
        pet_type: An[Literal[1], c_short(1)]
        meows: Int

    class _IntTaggedDog(CModel):
        pet_type: An[Literal[2], c_int(1)]
        barks: Float
        trained: Bool

    with pytest.raises(ValueError, match="same tag schema"):

        class _MismatchedEnvelope(CModel):
            pet: An[_ShortTaggedCat | _IntTaggedDog, Discriminator("pet_type")]


class LittleEndianPoint(CModel, c_endian_type="little", c_size_type="standard"):
    x: Int
    y: Int


class BigEndianPoint(CModel, c_endian_type="big", c_size_type="standard"):
    x: Int
    y: Int


class NetworkPoint(CModel, c_endian_type="network", c_size_type="standard"):
    x: Int
    y: Int


class NativeStandardPoint(CModel, c_endian_type="native", c_size_type="standard"):
    x: Int
    y: Int


class PackedLittleEndianMixed(
    CModel, c_alignment=1, c_endian_type="little", c_size_type="standard"
):
    count: Int
    flag: Bool
    value: Float


@pytest.mark.parametrize(
    ("model_cls", "prefix"),
    [
        (LittleEndianPoint, "<"),
        (BigEndianPoint, ">"),
        (NetworkPoint, "!"),
        (NativeStandardPoint, "="),
    ],
)
def test_endian_type_pack(model_cls, prefix):
    model = model_cls(x=3, y=7)
    buf = BytesIO()
    model.c_pack(buf)
    assert buf.getvalue() == struct.pack(f"{prefix}ii", 3, 7)


@pytest.mark.parametrize(
    ("model_cls", "prefix"),
    [
        (LittleEndianPoint, "<"),
        (BigEndianPoint, ">"),
        (NetworkPoint, "!"),
        (NativeStandardPoint, "="),
    ],
)
def test_endian_type_unpack(model_cls, prefix):
    buf = BytesIO(struct.pack(f"{prefix}ii", 3, 7))
    result = model_cls.c_unpack(buf)
    assert result.x == 3
    assert result.y == 7


@pytest.mark.parametrize(
    "model_cls",
    [LittleEndianPoint, BigEndianPoint, NetworkPoint, NativeStandardPoint],
)
def test_endian_type_roundtrip(model_cls):
    original = model_cls(x=42, y=-1)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert model_cls.c_unpack(buf) == original


def test_little_and_big_endian_differ():
    le_buf = BytesIO()
    LittleEndianPoint(x=1, y=2).c_pack(le_buf)
    be_buf = BytesIO()
    BigEndianPoint(x=1, y=2).c_pack(be_buf)
    assert le_buf.getvalue() != be_buf.getvalue()


def test_packed_little_endian_roundtrip():
    original = PackedLittleEndianMixed(count=5, flag=True, value=1.5)
    buf = BytesIO()
    original.c_pack(buf)

    packed_data = struct.pack("<i", 5) + struct.pack("<?", True) + struct.pack("<f", 1.5)
    assert buf.getvalue() == packed_data

    buf.seek(0)
    assert PackedLittleEndianMixed.c_unpack(buf) == original


def test_invalid_endian_size_combination():
    with pytest.raises(ValueError, match="Invalid combination"):

        class _BadModel(CModel, c_endian_type="little", c_size_type="native"):
            x: Int


def test_endian_type_inherited():
    class Parent(CModel, c_endian_type="big", c_size_type="standard"):
        x: Int

    class Child(Parent):
        y: Int

    assert Child.c_endian_type == "big"
    assert Child.c_size_type == "standard"

    buf = BytesIO()
    Child(x=1, y=2).c_pack(buf)
    assert buf.getvalue() == struct.pack(">ii", 1, 2)


def test_endian_type_overridden_by_subclass():
    class Parent(CModel, c_endian_type="big", c_size_type="standard"):
        x: Int

    class Child(Parent, c_endian_type="little"):
        y: Int

    assert Child.c_endian_type == "little"
    assert Child.c_size_type == "standard"

    buf = BytesIO()
    Child(x=1, y=2).c_pack(buf)
    assert buf.getvalue() == struct.pack("<ii", 1, 2)
