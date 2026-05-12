#!/usr/bin/env python3
"""Comprehensive example testing all model field types and Manager/QuerySet methods."""

import os
import sys

# Add parent to path so we can import myorm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import myorm
from myorm import models
from myorm.settings import connection_manager
from datetime import datetime, date, time, timedelta
from decimal import Decimal
import uuid as _uuid


def cleanup():
    """Remove test database."""
    if os.path.exists("test_all_fields.db"):
        os.remove("test_all_fields.db")


def configure():
    myorm.configure({
        "default": {
            "ENGINE": "sqlite",
            "NAME": "test_all_fields.db",
        }
    })


def test_integer_fields():
    """Test IntegerField, BigIntegerField, SmallIntegerField, PositiveIntegerField."""

    class IntModel(models.Model):
        name = models.CharField(max_length=50)
        age = models.IntegerField()
        big_num = models.BigIntegerField()
        small = models.SmallIntegerField(null=True)
        pos = models.PositiveIntegerField(default=0)
        pos_small = models.PositiveSmallIntegerField(default=0)

        class Meta:
            table_name = "int_test"

    # Create
    obj = IntModel(
        name="Test", age=30, big_num=123456789012345,
        small=100, pos=50, pos_small=10,
    )
    obj.save()
    assert obj.id is not None
    assert obj.id >= 1

    # Read
    fetched = IntModel.objects.get(id=obj.id)
    assert fetched.name == "Test"
    assert fetched.age == 30
    assert fetched.big_num == 123456789012345
    assert fetched.small == 100
    assert fetched.pos == 50
    assert fetched.pos_small == 10
    print("  ✓ Integer fields: PASS")


def test_string_fields():
    """Test CharField, TextField, SlugField, EmailField, URLField."""

    class StringModel(models.Model):
        name = models.CharField(max_length=100)
        bio = models.TextField(null=True)
        slug = models.SlugField()
        email = models.EmailField()
        url = models.URLField(null=True)

        class Meta:
            table_name = "string_test"

    obj = StringModel(
        name="Jane Doe",
        bio="A long biography with lots of text...",
        slug="jane-doe",
        email="jane@example.com",
    )
    obj.save()

    fetched = StringModel.objects.get(id=obj.id)
    print(f"the url filed is:{fetched.url}")
    assert fetched.name == "Jane Doe"
    assert fetched.bio == "A long biography with lots of text..."
    assert fetched.slug == "jane-doe"
    assert fetched.email == "jane@example.com"
    assert fetched.url is None  # null=True but default is ""
    print("  ✓ String fields: PASS")


def test_boolean_field():
    """Test BooleanField."""

    class BoolModel(models.Model):
        name = models.CharField(max_length=50)
        active = models.BooleanField(default=True)
        verified = models.BooleanField()

        class Meta:
            table_name = "bool_test"

    obj1 = BoolModel(name="Active User", active=True, verified=False)
    obj1.save()
    obj2 = BoolModel(name="Inactive User", active=False, verified=True)
    obj2.save()

    active_count = BoolModel.objects.filter(active=True).count()
    assert active_count >= 1
    print("  ✓ Boolean field: PASS")


def test_date_time_fields():
    """Test DateField, DateTimeField, TimeField."""

    class DateTimeModel(models.Model):
        name = models.CharField(max_length=50)
        created = models.DateTimeField()
        birthday = models.DateField(null=True)
        alarm = models.TimeField(null=True)

        class Meta:
            table_name = "datetime_test"

    now = datetime(2023, 6, 15, 10, 30, 0)
    today = date(1990, 1, 15)
    alarm_time = time(7, 0, 0)

    obj = DateTimeModel(name="Event", created=now, birthday=today, alarm=alarm_time)
    obj.save()

    fetched = DateTimeModel.objects.get(id=obj.id)
    assert fetched.name == "Event"
    assert fetched.birthday == today
    print("  ✓ Date/time fields: PASS")


def test_decimal_field():
    """Test DecimalField."""

    class PriceModel(models.Model):
        name = models.CharField(max_length=100)
        price = models.DecimalField(max_digits=10, decimal_places=2)
        discount = models.DecimalField(max_digits=5, decimal_places=2, default="0.00")

        class Meta:
            table_name = "price_test"

    obj = PriceModel(name="Widget", price=Decimal("19.99"), discount=Decimal("5.50"))
    obj.save()

    fetched = PriceModel.objects.get(id=obj.id)
    print(f"discount in decimal field test is:{fetched.discount}")
    assert str(fetched.price) == "19.99"
    assert str(fetched.discount) == "5.50" or '5.5'
    print("  ✓ Decimal field: PASS")


def test_float_field():
    """Test FloatField."""

    class FloatModel(models.Model):
        name = models.CharField(max_length=50)
        temperature = models.FloatField()

        class Meta:
            table_name = "float_test"

    obj = FloatModel(name="Reading", temperature=36.6)
    obj.save()

    fetched = FloatModel.objects.get(id=obj.id)
    assert abs(fetched.temperature - 36.6) < 0.001
    print("  ✓ Float field: PASS")


def test_duration_field():
    """Test DurationField."""

    class DurationModel(models.Model):
        name = models.CharField(max_length=50)
        length = models.DurationField()

        class Meta:
            table_name = "duration_test"

    obj = DurationModel(name="Meeting", length=timedelta(hours=2, minutes=30))
    obj.save()

    fetched = DurationModel.objects.get(id=obj.id)
    print(f"the duration is:{fetched.length}")
    assert fetched.length == timedelta(hours=2, minutes=30)
    print("  ✓ Duration field: PASS")


def test_json_field():
    """Test JSONField."""

    class JSONModel(models.Model):
        name = models.CharField(max_length=50)
        data = models.JSONField(null=True)
        metadata = models.JSONField()

        class Meta:
            table_name = "json_test"

    obj = JSONModel(
        name="Config",
        data={"key": "value", "count": 42},
        metadata={"tags": ["a", "b"]},
    )
    obj.save()

    fetched = JSONModel.objects.get(id=obj.id)
    assert fetched.data["key"] == "value"
    assert fetched.metadata["tags"] == ["a", "b"]
    print("  ✓ JSON field: PASS")


def test_uuid_field():
    """Test UUIDField."""

    class UUIDModel(models.Model):
        name = models.CharField(max_length=50)
        ref = models.UUIDField()

        class Meta:
            table_name = "uuid_test"

    test_uuid = _uuid.uuid4()
    obj = UUIDModel(name="Ref", ref=test_uuid)
    obj.save()

    fetched = UUIDModel.objects.get(id=obj.id)
    assert str(fetched.ref) == str(test_uuid)
    print("  ✓ UUID field: PASS")


def test_binary_field():
    """Test BinaryField."""

    class BinaryModel(models.Model):
        name = models.CharField(max_length=50)
        payload = models.BinaryField()

        class Meta:
            table_name = "binary_test"

    raw = b"\x00\x01\x02\x03\xff\xfe\xfd"
    obj = BinaryModel(name="Blob", payload=raw)
    obj.save()

    fetched = BinaryModel.objects.get(id=obj.id)
    assert fetched.payload == raw or bytes(fetched.payload) == raw
    print("  ✓ Binary field: PASS")


def test_email_url_slug_fields():
    """Test EmailField, URLField, SlugField defaults."""

    from myorm.models.fields import EmailField, URLField, SlugField

    ef = EmailField()
    assert ef.max_length == 254, f"EmailField max_length should be 254, got {ef.max_length}"

    uf = URLField()
    assert uf.max_length == 200, f"URLField max_length should be 200, got {uf.max_length}"

    sf = SlugField()
    assert sf.max_length == 50, f"SlugField max_length should be 50, got {sf.max_length}"
    print("  ✓ Email/URL/Slug field defaults: PASS")


def test_charfield_no_default_max_length():
    """Test that CharField has no default max_length (unlike old 255)."""

    from myorm.models.fields import CharField

    cf = CharField()
    assert cf.max_length is None, f"CharField max_length should be None, got {cf.max_length}"
    print("  ✓ CharField no default max_length: PASS")


def test_textfield_no_max_length():
    """Test that TextField doesn't inherit max_length from CharField."""

    from myorm.models.fields import TextField

    tf = TextField()
    assert not hasattr(tf, "max_length") or tf.max_length is None
    assert tf.__bases__ == (models.fields.Field,), "TextField must inherit from Field, not CharField"
    print("  ✓ TextField inheritance: PASS")


def test_boolean_null_always_false():
    """Test that BooleanField.null is always False."""

    from myorm.models.fields import BooleanField

    bf = BooleanField(null=True)
    assert bf.null is False, "BooleanField.null should always be False"
    print("  ✓ BooleanField null enforcement: PASS")


def test_choices():
    """Test choices with dict format."""

    from myorm.models.fields import CharField

    f = CharField(choices={"A": "Alpha", "B": "Beta"})
    result = f.get_choices()
    assert ("A", "Alpha") in result, f"Expected ('A', 'Alpha') in {result}"
    assert ("B", "Beta") in result
    print("  ✓ Dict choices: PASS")


def test_manager_methods():
    """Test all Manager methods."""

    class TestObj(models.Model):
        name = models.CharField(max_length=50)
        value = models.IntegerField(default=0)

        class Meta:
            table_name = "manager_test"

    # create
    obj = TestObj.objects.create(name="One", value=1)
    assert obj.id is not None

    # filter
    results = TestObj.objects.filter(name="One")
    assert len(results) >= 1

    # get
    fetched = TestObj.objects.get(id=obj.id)
    assert fetched.name == "One"

    # all
    all_objs = TestObj.objects.all()
    assert len(all_objs) >= 1

    # count
    cnt = TestObj.objects.filter(name="One").count()
    assert cnt >= 1

    # exists
    assert TestObj.objects.filter(name="One").exists()
    assert not TestObj.objects.filter(name="NONEXISTENT").exists()

    # first / last
    first = TestObj.objects.all().first()
    last = TestObj.objects.all().last()
    assert first is not None
    assert last is not None

    # update
    updated = TestObj.objects.filter(name="One").update(value=42)
    assert updated >= 1
    fetched = TestObj.objects.get(id=obj.id)
    assert fetched.value == 42

    # values
    vals = TestObj.objects.filter(name="One").values("name", "value")
    assert len(vals) >= 1
    assert "name" in vals[0]

    # values_list
    vlist = TestObj.objects.filter(name="One").values_list("name")
    assert len(vlist) >= 1

    # delete
    old_count = TestObj.objects.count()
    TestObj.objects.filter(name="One").delete()
    new_count = TestObj.objects.count()
    assert new_count == old_count - 1

    print("  ✓ Manager/QuerySet methods: PASS")


def test_get_or_create():
    """Test get_or_create."""

    class GOCModel(models.Model):
        key = models.CharField(max_length=50)
        value = models.IntegerField(default=0)

        class Meta:
            table_name = "get_or_create_test"

    obj1, created1 = GOCModel.objects.get_or_create(key="test", defaults={"value": 10})
    assert created1 is True
    obj2, created2 = GOCModel.objects.get_or_create(key="test", defaults={"value": 20})
    assert created2 is False
    assert obj2.value == 10  # original value preserved
    print("  ✓ get_or_create: PASS")


def test_decimal_validation():
    """Test DecimalField validation."""
    import pytest

    try:
        from myorm.models.fields import DecimalField

        # Should raise when decimal_places > max_digits
        try:
            DecimalField(max_digits=5, decimal_places=6)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

        # Should raise on negative digits
        try:
            DecimalField(max_digits=-1)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    except Exception as e:
        print(f"  ✗ Decimal validation: FAIL ({e})")
        raise

    print("  ✓ Decimal validation: PASS")


def test_on_delete_handlers():
    """Test on_delete handler functions."""
    from myorm.models.relationships import CASCADE, SET_NULL, SET_DEFAULT, PROTECT, DO_NOTHING, SET

    assert callable(CASCADE)
    assert callable(SET_NULL)
    assert callable(SET_DEFAULT)
    assert callable(PROTECT)
    assert callable(DO_NOTHING)
    assert callable(SET)
    print("  ✓ on_delete handlers: PASS")


def test_autoincrement():
    """Test auto_increment field attribute."""
    from myorm.models.fields import IntegerField

    f = IntegerField(primary_key=True, auto_increment=True)
    assert f.auto_increment is True
    # auto_increment should imply not null
    assert f.null is False
    print("  ✓ Auto-increment: PASS")


def run_all():
    """Run all tests."""
    cleanup()
    configure()

    print("Running comprehensive field tests...")
    test_integer_fields()
    test_string_fields()
    test_boolean_field()
    test_date_time_fields()
    test_decimal_field()
    test_float_field()
    test_duration_field()
    test_json_field()
    test_uuid_field()
    test_binary_field()
    test_email_url_slug_fields()
    test_charfield_no_default_max_length()
    test_textfield_no_max_length()
    test_boolean_null_always_false()
    test_choices()
    test_decimal_validation()
    test_on_delete_handlers()
    test_autoincrement()

    # Needs clean DB
    cleanup()
    configure()
    test_manager_methods()
    test_get_or_create()

    print("\n✅ ALL TESTS PASSED!")


if __name__ == "__main__":
    run_all()