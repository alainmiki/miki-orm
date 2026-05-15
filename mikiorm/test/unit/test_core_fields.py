"""Core field types: create, read, update, delete, defaults, null handling."""

import datetime
import uuid
from decimal import Decimal

import pytest

from mikiorm import atomic, configure, settings
from mikiorm.models.base import Model
from mikiorm.models.fields import (
    AutoField, CharField, TextField, BooleanField, IntegerField,
    BigIntegerField, SmallIntegerField, PositiveIntegerField, PositiveSmallIntegerField,
    FloatField, DecimalField, DateTimeField, DateField, TimeField, UUIDField,
    JSONField, BinaryField, EmailField, URLField, SlugField, GenericIPAddressField, FilePathField,
    ForeignKey,
)
from mikiorm.models.relationships import CASCADE, SET_NULL


# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class CoreFieldsModel(Model):
    name = CharField(max_length=100)
    description = TextField(null=True, blank=True)
    is_active = BooleanField(default=True)
    count = IntegerField(default=0)
    big = BigIntegerField(default=0)
    small = SmallIntegerField(default=0)
    pos = PositiveIntegerField(default=0)
    pos_small = PositiveSmallIntegerField(default=0)
    rating = FloatField(null=True)
    price = DecimalField(max_digits=10, decimal_places=2, null=True)
    created = DateTimeField(auto_now_add=True)
    birth = DateField(null=True)
    start = TimeField(null=True)
    duration = DecimalField(null=True)  # stored as numeric (seconds)
    tag = UUIDField(null=True)
    meta = JSONField(default=dict)
    data = BinaryField(null=True)
    url = URLField(null=True)
    ip = GenericIPAddressField(null=True)
    file = FilePathField(path="/tmp", null=True)

    class Meta:
        table_name = "core_fields"


class Person(Model):
    email = EmailField(unique=True)
    age = IntegerField(null=True)

    class Meta:
        table_name = "people"


# ---------------------------------------------------------------------------
# Database configuration fixture
# ---------------------------------------------------------------------------


def get_config(backend):
    if backend == "sqlite":
        return {"ENGINE": "sqlite", "NAME": ":memory:"}
    elif backend == "postgres":
        return {
            "ENGINE": "postgresql",
            "NAME": "miki_orm_test",
            "USER": "postgres",
            "PASSWORD": "admin",
            "HOST": "localhost",
            "PORT": 5432,
        }
    else:
        raise ValueError(backend)


@pytest.fixture(scope="module", params=["sqlite", "postgres"])
def db_config(request):
    backend = request.param
    configure(databases={"default": get_config(backend)})
    yield backend
    try:
        settings.connection_manager.close_all()
    except Exception:
        pass


def ensure_table(model):
    """Ensure table exists before tests."""
    model._table_created = False
    dummy = model()
    for fname, fobj in model._meta.fields.items():
        if not fobj.null and not isinstance(fobj, AutoField):
            if isinstance(fobj, CharField):
                setattr(dummy, fname, "x")
            elif isinstance(fobj, IntegerField):
                setattr(dummy, fname, 0)
            elif isinstance(fobj, BooleanField):
                setattr(dummy, fname, True)
            elif isinstance(fobj, DecimalField):
                setattr(dummy, fname, Decimal("0.00"))
            elif isinstance(fobj, FloatField):
                setattr(dummy, fname, 0.0)
            elif isinstance(fobj, DateField):
                setattr(dummy, fname, datetime.date.today())
            elif isinstance(fobj, DateTimeField):
                setattr(dummy, fname, datetime.datetime.now())
            elif isinstance(fobj, TimeField):
                setattr(dummy, fname, datetime.time(0, 0))
            elif isinstance(fobj, UUIDField):
                setattr(dummy, fname, uuid.uuid4())
            elif isinstance(fobj, JSONField):
                setattr(dummy, fname, {})
            elif isinstance(fobj, BinaryField):
                setattr(dummy, fname, b"")
            elif isinstance(fobj, URLField):
                setattr(dummy, fname, "http://x.com")
            elif isinstance(fobj, EmailField):
                setattr(dummy, fname, "x@x.com")
            elif isinstance(fobj, GenericIPAddressField):
                setattr(dummy, fname, "127.0.0.1")
            elif isinstance(fobj, FilePathField):
                setattr(dummy, fname, "/tmp")
            else:
                setattr(dummy, fname, None)
    try:
        dummy.save(force_insert=True)
    except Exception:
        pass


def clear_table(model):
    try:
        conn = settings.connection_manager.get_connection()
        table = model._meta.table_name
        conn.execute(f"DELETE FROM {table}", ())
        conn.commit()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_db(db_config):
    ensure_table(CoreFieldsModel)
    ensure_table(Person)
    yield
    clear_table(CoreFieldsModel)
    clear_table(Person)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_char_and_text_fields(db_config):
    m = CoreFieldsModel.objects.create(name="Test Name")
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.name == "Test Name"
    assert fetched.description is None

    fetched.description = "Some Description"
    fetched.save()
    fetched2 = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched2.description == "Some Description"


def test_boolean_field(db_config):
    m = CoreFieldsModel.objects.create(name="BoolTest")
    assert m.is_active is True
    m.is_active = False
    m.save()
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.is_active is False


def test_integer_fields(db_config):
    m = CoreFieldsModel.objects.create(name="IntTest", count=5, big=2**40, small=-100, pos=50, pos_small=10)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.count == 5
    assert fetched.big == 2**40
    assert fetched.small == -100
    assert fetched.pos == 50
    assert fetched.pos_small == 10


def test_float_and_decimal(db_config):
    m = CoreFieldsModel.objects.create(name="FloatTest", rating=4.5, price=Decimal("19.99"))
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert abs(fetched.rating - 4.5) < 0.01
    assert abs(fetched.price - Decimal("19.99")) < Decimal("0.01")


def test_datetime_date_time_fields(db_config):
    now = datetime.datetime.now()
    today = datetime.date.today()
    time_now = datetime.time(now.hour, now.minute, now.second)
    m = CoreFieldsModel.objects.create(name="DateTimeTest", birth=today, start=time_now)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.birth == today
    assert fetched.start == time_now
    assert fetched.created > now - datetime.timedelta(seconds=5)


def test_uuid_field(db_config):
    test_uuid = uuid.uuid4()
    m = CoreFieldsModel.objects.create(name="UUIDTest", tag=test_uuid)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.tag == test_uuid


def test_json_field(db_config):
    payload = {"nested": {"a": 1, "b": [2, 3]}, "list": [4, 5, 6]}
    m = CoreFieldsModel.objects.create(name="JSONTest", meta=payload)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.meta == payload


def test_binary_field(db_config):
    data = b"binary\x00\xff\xfe"
    m = CoreFieldsModel.objects.create(name="BinaryTest", data=data)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.data == data


def test_url_and_ip_fields(db_config):
    m = CoreFieldsModel.objects.create(name="NetworkTest", url="https://example.org", ip="10.0.0.1")
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.url == "https://example.org"
    assert fetched.ip == "10.0.0.1"


def test_filepath_field(db_config):
    m = CoreFieldsModel.objects.create(name="FileTest", file="/var/log/syslog")
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.file == "/var/log/syslog"


def test_email_field_unique(db_config):
    Person.objects.create(email="unique1@example.com", age=30)
    with pytest.raises(Exception):
        Person.objects.create(email="unique1@example.com", age=25)


def test_empty_string_and_null_handling(db_config):
    m = CoreFieldsModel.objects.create(name="", description=None)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.name == ""
    assert fetched.description is None


def test_default_values(db_config):
    p = Person.objects.create(email="default@example.com")
    assert p.age is None  # IntegerField with null=True defaults to None


def test_bigint_range(db_config):
    m = CoreFieldsModel.objects.create(name="Big", big=2**63 - 1)
    fetched = CoreFieldsModel.objects.get(pk=m.pk)
    assert fetched.big == 2**63 - 1


def test_positive_integer_negative_rejected(db_config):
    # Should raise either at validation or DB constraint
    with pytest.raises(Exception):
        CoreFieldsModel.objects.create(name="NegativePos", pos=-1)
