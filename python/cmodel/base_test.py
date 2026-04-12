import ctypes
import math
import struct
from io import BytesIO
from typing import Annotated as An
from typing import Literal

import pytest
from pydantic import Discriminator

from cmodel.base import CEncoded
from cmodel.base import CModel
from cmodel.schema import CEncoderSchema
from cmodel.types import Bool
from cmodel.types import Double
from cmodel.types import Float
from cmodel.types import Int
from cmodel.types import RawBytes
from cmodel.types import Short
from cmodel.types import SignedChar
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


class TrailingBytesModel(CModel):
    header: Int
    data: RawBytes


def test_c_encoded_raw_bytes_unpack():
    payload = struct.pack("i", 42) + b"\xde\xad\xbe\xef"
    result = TrailingBytesModel.c_unpack(BytesIO(payload))
    assert result.header == 42
    assert result.data == b"\xde\xad\xbe\xef"


def test_c_encoded_raw_bytes_pack():
    model = TrailingBytesModel(header=42, data=b"\xde\xad\xbe\xef")
    buf = BytesIO()
    model.c_pack(buf)
    assert buf.getvalue() == struct.pack("i", 42) + b"\xde\xad\xbe\xef"


def test_c_encoded_raw_bytes_roundtrip():
    # data length must be multiple of struct alignment (4) to survive trailing padding
    original = TrailingBytesModel(header=7, data=b"\x01\x02\x03\x04")
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert TrailingBytesModel.c_unpack(buf) == original


def test_c_encoded_raw_bytes_empty_trailing():
    payload = struct.pack("i", 0)
    result = TrailingBytesModel.c_unpack(BytesIO(payload))
    assert result.header == 0
    assert result.data == b""


def test_c_encoded_custom_encoder():
    """CEncoded with custom fixed-size encoder that doubles an int on pack and halves on unpack."""

    def make_encoder(endian: str, size: str) -> CEncoderSchema[int]:
        prefix = {"native": "@", "little": "<", "big": ">"}[endian]
        fmt = struct.Struct(f"{prefix}i")
        return CEncoderSchema[int](
            type="encoder",
            alignment=fmt.size,
            size=fmt.size,
            unpack=lambda buf: fmt.unpack(buf.read(fmt.size))[0] // 2,
            pack=lambda buf, v: buf.write(fmt.pack(v * 2)),
            schema_equality_info=("test", "doubler"),
        )

    class DoublerModel(CModel):
        value: An[int, CEncoded(get_encoder=make_encoder)]

    buf = BytesIO()
    DoublerModel(value=5).c_pack(buf)
    # packed value should be 10 (doubled)
    assert struct.unpack("i", buf.getvalue())[0] == 10

    buf.seek(0)
    result = DoublerModel.c_unpack(buf)
    # unpacked value should be halved back to 5
    assert result.value == 5


def test_c_encoded_receives_endian_and_size_type():
    """Verify encoder factory receives struct's endian_type and size_type."""
    captured = {}

    def capturing_encoder(endian: str, size: str) -> CEncoderSchema[int]:
        captured["endian"] = endian
        captured["size"] = size
        fmt = struct.Struct("<i")
        return CEncoderSchema[int](
            type="encoder",
            alignment=4,
            size=4,
            unpack=lambda buf: fmt.unpack(buf.read(4))[0],
            pack=lambda buf, v: buf.write(fmt.pack(v)),
            schema_equality_info=("test", "capture"),
        )

    class CaptureModel(CModel, c_endian_type="big", c_size_type="standard"):
        val: An[int, CEncoded(get_encoder=capturing_encoder)]

    assert captured["endian"] == "big"
    assert captured["size"] == "standard"


class _DefaultModel(CModel):
    count: Int
    flag: Bool = True


def test_default_field_unpack():
    buf = BytesIO(struct.pack("i?", 5, False))
    result = _DefaultModel.c_unpack(buf)
    assert result.count == 5
    assert result.flag is False


def test_default_field_pack():
    buf = BytesIO()
    _DefaultModel(count=5).c_pack(buf)
    # Include trailing padding to match struct alignment
    expected = struct.pack("i?", 5, True) + b"\x00" * 3
    assert buf.getvalue() == expected


def test_default_field_roundtrip():
    original = _DefaultModel(count=7, flag=False)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert _DefaultModel.c_unpack(buf) == original


class _FixedCat(CModel):
    pet_type: An[Literal[1], c_int(1)]
    meows: Int


class _VariableDog(CModel):
    pet_type: An[Literal[2], c_int(1)]
    sound: RawBytes


class _MixedUnionEnvelope(CModel):
    pet: An[_FixedCat | _VariableDog, Discriminator("pet_type")]


def test_mixed_tagged_union_fixed_variant_roundtrip():
    original = _MixedUnionEnvelope(pet=_FixedCat(pet_type=1, meows=7))
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert _MixedUnionEnvelope.c_unpack(buf) == original


def test_mixed_tagged_union_variable_variant_roundtrip():
    original = _MixedUnionEnvelope(pet=_VariableDog(pet_type=2, sound=b"\xaa\xbb\xcc\xdd"))
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert _MixedUnionEnvelope.c_unpack(buf) == original


def test_mixed_tagged_union_unpack_fixed():
    buf = BytesIO(struct.pack("ii", 1, 42))
    result = _MixedUnionEnvelope.c_unpack(buf)
    assert result.pet == _FixedCat(pet_type=1, meows=42)


def test_mixed_tagged_union_unpack_variable():
    buf = BytesIO(struct.pack("i", 2) + b"\xde\xad")
    result = _MixedUnionEnvelope.c_unpack(buf)
    assert result.pet == _VariableDog(pet_type=2, sound=b"\xde\xad")


class MixedAlignmentModel(CModel):
    """double(8) + signed_char(1) + int(4) — tests per-field alignment padding."""

    d: Double
    c: SignedChar
    i: Int


def test_mixed_alignment_matches_c_struct():
    """CModel layout must match C struct layout for fields with different alignments."""
    expected = struct.pack("@dbi", 1.5, 97, 42)
    buf = BytesIO()
    MixedAlignmentModel(d=1.5, c=97, i=42).c_pack(buf)
    assert buf.getvalue() == expected


def test_mixed_alignment_unpack():
    data = struct.pack("@dbi", 1.5, 97, 42)
    result = MixedAlignmentModel.c_unpack(BytesIO(data))
    assert result.d == 1.5  # noqa: RUF069
    assert result.c == 97
    assert result.i == 42


def test_mixed_alignment_roundtrip():
    original = MixedAlignmentModel(d=1.5, c=97, i=42)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert MixedAlignmentModel.c_unpack(buf) == original


class ShortDoubleModel(CModel):
    """short(2) + double(8) — double needs 8-byte alignment after a 2-byte field."""

    s: Short
    d: Double


def test_short_double_matches_c_struct():
    expected = struct.pack("@hd", 5, 1.23)
    buf = BytesIO()
    ShortDoubleModel(s=5, d=1.23).c_pack(buf)
    assert buf.getvalue() == expected


def test_short_double_roundtrip():
    original = ShortDoubleModel(s=5, d=1.23)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert ShortDoubleModel.c_unpack(buf) == original


class InnerMixed(CModel):
    """char(1) + double(8) — inner struct has 8-byte alignment."""

    c: SignedChar
    d: Double


class OuterMixed(CModel):
    """short(2) + InnerMixed(align 8) + int(4) — nested struct forces alignment gaps."""

    s: Short
    inner: InnerMixed
    i: Int


class _CInnerMixed(ctypes.Structure):
    _fields_ = [("c", ctypes.c_byte), ("d", ctypes.c_double)]


class _COuterMixed(ctypes.Structure):
    _fields_ = [("s", ctypes.c_short), ("inner", _CInnerMixed), ("i", ctypes.c_int)]


def test_nested_mixed_alignment_matches_c_struct():
    c_outer = bytes(_COuterMixed(s=5, inner=_CInnerMixed(c=97, d=math.pi), i=42))
    buf = BytesIO()
    OuterMixed(s=5, inner=InnerMixed(c=97, d=math.pi), i=42).c_pack(buf)
    assert buf.getvalue() == c_outer


def test_nested_mixed_alignment_unpack():
    buf = BytesIO()
    original = OuterMixed(s=5, inner=InnerMixed(c=97, d=math.pi), i=42)
    original.c_pack(buf)
    buf.seek(0)
    result = OuterMixed.c_unpack(buf)
    assert result.s == 5
    assert result.inner.c == 97
    assert result.inner.d == pytest.approx(math.pi)
    assert result.i == 42


def test_nested_mixed_alignment_roundtrip():
    original = OuterMixed(s=5, inner=InnerMixed(c=97, d=math.pi), i=42)
    buf = BytesIO()
    original.c_pack(buf)
    buf.seek(0)
    assert OuterMixed.c_unpack(buf) == original
