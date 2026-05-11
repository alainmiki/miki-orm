"""Comprehensive field tests — mirroring Django 6.0 field behaviour."""

from __future__ import annotations

import pytest
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import uuid as _uuid

from myorm.models.fields import (
    AutoField, BigAutoField, SmallAutoField,
    IntegerField, BigIntegerField, SmallIntegerField,
    PositiveIntegerField, PositiveSmallIntegerField,
    CharField, TextField,
    BooleanField,
    DateTimeField, DateField, TimeField,
    DecimalField, DurationField, FloatField,
    JSONField, UUIDField, BinaryField,
    EmailField, URLField, SlugField,
    FilePathField, GenericIPAddressField,
    Field,
)
from myorm.models.relationships import (
    ForeignKey, OneToOneField, ManyToManyField,
    CASCADE, SET_NULL, SET_DEFAULT, PROTECT, DO_NOTHING, SET,
)


# ---------------------------------------------------------------------------
# Base field
# ---------------------------------------------------------------------------

class TestFieldBase:
    def test_primary_key_implies_null_false_and_unique_true(self):
        f = IntegerField(primary_key=True)
        assert f.primary_key is True
        assert f.null is False
        assert f.unique is True

    def test_auto_increment_on_field(self):
        f = IntegerField(primary_key=True, auto_increment=True)
        assert f.auto_increment is True

    def test_auto_increment_implies_not_null(self):
        f = IntegerField(auto_increment=True)
        assert f.null is False

    def test_repr_includes_name_and_primary_key(self):
        f = IntegerField(primary_key=True)
        f.name = "id"
        r = repr(f)
        assert "name='id'" in r
        assert "primary_key=True" in r


# ---------------------------------------------------------------------------
# Integer fields
# ---------------------------------------------------------------------------

class TestIntegerField:
    def test_default_value(self):
        f = IntegerField()
        assert f.python_value(None) == 0

    def test_null_returns_none(self):
        f = IntegerField(null=True)
        assert f.python_value(None) is None

    def test_convert_string_to_int(self):
        f = IntegerField()
        assert f.python_value("42") == 42

    def test_db_value_none(self):
        f = IntegerField(null=True)
        assert f.db_value(None) is None

    def test_db_value_int(self):
        f = IntegerField()
        assert f.db_value(42) == 42

    def test_get_internal_type(self):
        assert IntegerField().get_internal_type() == "IntegerField"


class TestBigIntegerField:
    def test_large_value(self):
        f = BigIntegerField()
        val = 9223372036854775807
        assert f.python_value(val) == val

    def test_get_internal_type(self):
        assert BigIntegerField().get_internal_type() == "BigIntegerField"


class TestSmallIntegerField:
    def test_small_value(self):
        f = SmallIntegerField()
        assert f.python_value(100) == 100

    def test_get_internal_type(self):
        assert SmallIntegerField().get_internal_type() == "SmallIntegerField"


class TestPositiveIntegerField:
    def test_positive_value(self):
        f = PositiveIntegerField()
        assert f.python_value(10) == 10

    def test_zero_is_ok(self):
        f = PositiveIntegerField()
        assert f.python_value(0) == 0

    def test_negative_raises(self):
        f = PositiveIntegerField()
        with pytest.raises(ValueError):
            f.python_value(-1)


class TestPositiveSmallIntegerField:
    def test_positive_small_value(self):
        f = PositiveSmallIntegerField()
        assert f.python_value(10) == 10

    def test_negative_raises(self):
        f = PositiveSmallIntegerField()
        with pytest.raises(ValueError):
            f.python_value(-5)


class TestAutoField:
    def test_primary_key_by_default(self):
        f = AutoField()
        assert f.primary_key is True
        assert f.null is False

    def test_db_value_none(self):
        f = AutoField()
        assert f.db_value(None) is None


class TestBigAutoField:
    def test_primary_key(self):
        f = BigAutoField()
        assert f.primary_key is True


class TestSmallAutoField:
    def test_primary_key(self):
        f = SmallAutoField()
        assert f.primary_key is True


# ---------------------------------------------------------------------------
# CharField / TextField
# ---------------------------------------------------------------------------

class TestCharField:
    def test_max_length_none_by_default(self):
        """Unlike old code (255), Django 6.0 has max_length=None by default."""
        f = CharField()
        assert f.max_length is None

    def test_explicit_max_length(self):
        f = CharField(max_length=100)
        assert f.max_length == 100

    def test_db_value_none(self):
        f = CharField(null=True)
        assert f.db_value(None) is None

    def test_db_value_str(self):
        f = CharField()
        assert f.db_value("hello") == "hello"

    def test_null_not_allowed_by_default(self):
        f = CharField()
        assert f.python_value(None) == ""

    def test_null_allowed_when_set(self):
        f = CharField(null=True)
        assert f.python_value(None) is None


class TestTextField:
    def test_inherits_from_field_not_charfield(self):
        """TextField must inherit from Field, NOT CharField (Django design)."""
        assert TextField.__bases__ == (Field,)

    def test_no_max_length_attribute(self):
        """TextField should not have max_length."""
        tf = TextField()
        assert not hasattr(tf, "max_length") or tf.max_length is None

    def test_db_value(self):
        f = TextField(null=True)
        assert f.db_value(None) is None
        assert f.db_value("long text") == "long text"

    def test_get_internal_type(self):
        assert TextField().get_internal_type() == "TextField"


class TestSlugField:
    def test_default_max_length(self):
        f = SlugField()
        assert f.max_length == 50

    def test_custom_max_length(self):
        f = SlugField(max_length=100)
        assert f.max_length == 100

    def test_get_internal_type(self):
        assert SlugField().get_internal_type() == "SlugField"


class TestURLField:
    def test_default_max_length(self):
        f = URLField()
        assert f.max_length == 200

    def test_custom_max_length(self):
        f = URLField(max_length=500)
        assert f.max_length == 500


class TestEmailField:
    def test_default_max_length_is_254(self):
        """Django 6.0: EmailField default max_length is 254, NOT 255."""
        f = EmailField()
        assert f.max_length == 254

    def test_custom_max_length(self):
        f = EmailField(max_length=300)
        assert f.max_length == 300

    def test_get_internal_type(self):
        assert EmailField().get_internal_type() == "EmailField"


# ---------------------------------------------------------------------------
# Boolean field
# ---------------------------------------------------------------------------

class TestBooleanField:
    def test_null_is_always_false(self):
        """Django 6.0: BooleanField does not accept null=True."""
        f = BooleanField()
        assert f.null is False

        # Even if someone tries to force it
        f2 = BooleanField(null=True)
        assert f2.null is False  # overridden by field logic

    def test_none_maps_to_false(self):
        f = BooleanField()
        assert f.python_value(None) is False

    def test_truthy_values(self):
        f = BooleanField()
        assert f.python_value(1) is True
        assert f.python_value("yes") is True
        assert f.python_value(True) is True

    def test_falsy_values(self):
        f = BooleanField()
        assert f.python_value(0) is False
        assert f.python_value("") is False
        assert f.python_value(False) is False

    def test_db_value(self):
        f = BooleanField()
        assert f.db_value(True) == 1
        assert f.db_value(False) == 0


# ---------------------------------------------------------------------------
# Date/time fields
# ---------------------------------------------------------------------------

class TestDateTimeField:
    def test_valid_datetime(self):
        f = DateTimeField()
        dt = datetime(2023, 1, 15, 10, 30, 0)
        assert f.python_value(dt) is dt

    def test_none_returns_none_when_null(self):
        f = DateTimeField(null=True)
        assert f.python_value(None) is None

    def test_none_returns_min_when_not_null(self):
        f = DateTimeField()
        assert f.python_value(None) == datetime.min

    def test_rejects_date(self):
        f = DateTimeField()
        with pytest.raises(TypeError):
            f.python_value(date(2023, 1, 1))

    def test_auto_now_sets_editable_false(self):
        f = DateTimeField(auto_now=True)
        assert f.editable is False
        assert f.blank is True

    def test_auto_now_add_sets_editable_false(self):
        f = DateTimeField(auto_now_add=True)
        assert f.editable is False
        assert f.blank is True

    def test_auto_now_and_auto_now_add_conflict(self):
        with pytest.raises(ValueError):
            DateTimeField(auto_now=True, auto_now_add=True)

    def test_db_value_isoformat(self):
        f = DateTimeField()
        dt = datetime(2023, 6, 15, 10, 30, 45, 123456)
        result = f.db_value(dt)
        assert "2023-06-15 10:30:45" in result


class TestDateField:
    def test_valid_date(self):
        f = DateField()
        d = date(2023, 1, 15)
        assert f.python_value(d) is d

    def test_rejects_non_date(self):
        f = DateField()
        with pytest.raises(TypeError):
            f.python_value("2023-01-01")

    def test_null(self):
        f = DateField(null=True)
        assert f.python_value(None) is None

    def test_get_internal_type(self):
        assert DateField().get_internal_type() == "DateField"


class TestTimeField:
    def test_valid_time(self):
        f = TimeField()
        t = time(12, 30, 45)
        assert f.python_value(t) is t

    def test_rejects_non_time(self):
        f = TimeField()
        with pytest.raises(TypeError):
            f.python_value("12:30")

    def test_null(self):
        f = TimeField(null=True)
        assert f.python_value(None) is None


# ---------------------------------------------------------------------------
# Decimal / Float / Duration
# ---------------------------------------------------------------------------

class TestDecimalField:
    def test_valid_creation(self):
        f = DecimalField(max_digits=10, decimal_places=2)
        assert f.max_digits == 10
        assert f.decimal_places == 2

    def test_decimal_places_greater_than_max_digits_raises(self):
        with pytest.raises(ValueError):
            DecimalField(max_digits=5, decimal_places=6)

    def test_negative_max_digits_raises(self):
        with pytest.raises(ValueError):
            DecimalField(max_digits=-1)

    def test_negative_decimal_places_raises(self):
        with pytest.raises(ValueError):
            DecimalField(max_digits=5, decimal_places=-1)

    def test_python_value_returns_decimal(self):
        f = DecimalField(max_digits=10, decimal_places=2)
        result = f.python_value("99.99")
        assert isinstance(result, Decimal)
        assert result == Decimal("99.99")

    def test_null_returns_none(self):
        f = DecimalField(max_digits=10, decimal_places=2, null=True)
        assert f.python_value(None) is None

    def test_db_value_string(self):
        f = DecimalField(max_digits=10, decimal_places=2, null=True)
        assert f.db_value(None) is None
        assert f.db_value(Decimal("99.99")) == "99.99"


class TestFloatField:
    def test_basic(self):
        f = FloatField()
        assert f.python_value(3.14) == 3.14
        assert f.python_value("3.14") == 3.14

    def test_null(self):
        f = FloatField(null=True)
        assert f.python_value(None) is None

    def test_db_value(self):
        f = FloatField(null=True)
        assert f.db_value(None) is None
        assert f.db_value(3.14) == 3.14


class TestDurationField:
    def test_timedelta_value(self):
        f = DurationField()
        td = timedelta(hours=2, minutes=30)
        assert f.python_value(td) == td

    def test_rejects_non_timedelta(self):
        f = DurationField()
        with pytest.raises(TypeError):
            f.python_value("2 hours")

    def test_db_value_microseconds(self):
        f = DurationField()
        td = timedelta(hours=1)
        assert f.db_value(td) == 3_600_000_000

    def test_null(self):
        f = DurationField(null=True)
        assert f.python_value(None) is None
        assert f.db_value(None) is None


# ---------------------------------------------------------------------------
# JSON / UUID / Binary
# ---------------------------------------------------------------------------

class TestJSONField:
    def test_dict_value(self):
        f = JSONField()
        data = {"key": "value"}
        assert f.python_value(data) == data

    def test_string_parsed(self):
        f = JSONField()
        result = f.python_value('{"key": "value"}')
        assert result == {"key": "value"}

    def test_null(self):
        f = JSONField(null=True)
        assert f.python_value(None) is None

    def test_db_value_serializes(self):
        f = JSONField()
        result = f.db_value({"key": "value"})
        assert result == '{"key": "value"}'

    def test_default_empty_dict(self):
        f = JSONField()
        assert f.python_value(None) == {}


class TestUUIDField:
    def test_uuid_value(self):
        f = UUIDField()
        u = _uuid.uuid4()
        assert f.python_value(u) == u

    def test_string_uuid(self):
        f = UUIDField()
        u = _uuid.uuid4()
        result = f.python_value(str(u))
        assert result == u

    def test_null(self):
        f = UUIDField(null=True)
        assert f.python_value(None) is None

    def test_db_value(self):
        f = UUIDField(null=True)
        u = _uuid.uuid4()
        assert f.db_value(u) == str(u)
        assert f.db_value(None) is None


class TestBinaryField:
    def test_bytes_value(self):
        f = BinaryField()
        data = b"hello world"
        assert f.python_value(data) == data

    def test_bytearray_value(self):
        f = BinaryField()
        data = bytearray(b"hello")
        result = f.python_value(data)
        assert result == b"hello"
        assert isinstance(result, bytes)

    def test_rejects_invalid_type(self):
        f = BinaryField()
        with pytest.raises(TypeError):
            f.python_value("not bytes")

    def test_editable_false_by_default(self):
        f = BinaryField()
        assert f.editable is False


# ---------------------------------------------------------------------------
# Email / URL / Slug — default max_length
# ---------------------------------------------------------------------------

class TestEmailFieldDefaults:
    """Django 6.0: EmailField max_length default is 254, not 255."""

    def test_default_max_length_254(self):
        f = EmailField()
        assert f.max_length == 254

    def test_custom_max_length(self):
        f = EmailField(max_length=300)
        assert f.max_length == 300


class TestURLFieldDefaults:
    def test_default_max_length_200(self):
        f = URLField()
        assert f.max_length == 200


class TestSlugFieldDefaults:
    def test_default_max_length_50(self):
        f = SlugField()
        assert f.max_length == 50


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class TestChoices:
    def test_simple_choices(self):
        f = CharField(choices=[("A", "Alpha"), ("B", "Beta")])
        result = f.get_choices()
        assert result == [("A", "Alpha"), ("B", "Beta")]

    def test_dict_choices(self):
        f = CharField(choices={"A": "Alpha", "B": "Beta"})
        result = f.get_choices()
        assert ("A", "Alpha") in result
        assert ("B", "Beta") in result


# ---------------------------------------------------------------------------
# Deconstruct
# ---------------------------------------------------------------------------

class TestDeconstruct:
    def test_char_field_with_max_length(self):
        f = CharField(max_length=100)
        path, aname, args, kwargs = f.deconstruct()
        assert kwargs["max_length"] == 100

    def test_char_field_no_max_length(self):
        f = CharField()
        path, aname, args, kwargs = f.deconstruct()
        assert "max_length" not in kwargs

    def test_email_field_default_not_emitted(self):
        f = EmailField()
        path, aname, args, kwargs = f.deconstruct()
        assert "max_length" not in kwargs, "Default max_length=254 should not be emitted"

    def test_decimal_field(self):
        f = DecimalField(max_digits=10, decimal_places=2)
        path, aname, args, kwargs = f.deconstruct()
        assert kwargs["max_digits"] == 10
        assert kwargs["decimal_places"] == 2

    def test_boolean_field_no_null_emitted(self):
        f = BooleanField()
        path, aname, args, kwargs = f.deconstruct()
        assert "null" not in kwargs

    def test_integer_field_primary_key(self):
        f = IntegerField(primary_key=True)
        path, aname, args, kwargs = f.deconstruct()
        assert kwargs["primary_key"] is True
        assert kwargs["unique"] is True


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

class TestForeignKey:
    def test_on_delete_cascade(self):
        fk = ForeignKey(to="auth.User", on_delete=CASCADE)
        assert fk.on_delete is CASCADE

    def test_on_delete_set_null(self):
        fk = ForeignKey(to="auth.User", on_delete=SET_NULL)
        assert fk.on_delete is SET_NULL

    def test_on_delete_protect(self):
        fk = ForeignKey(to="auth.User", on_delete=PROTECT)
        assert fk.on_delete is PROTECT

    def test_on_delete_set_default(self):
        fk = ForeignKey(to="auth.User", on_delete=SET_DEFAULT)
        assert fk.on_delete is SET_DEFAULT

    def test_on_delete_do_nothing(self):
        fk = ForeignKey(to="auth.User", on_delete=DO_NOTHING)
        assert fk.on_delete is DO_NOTHING

    def test_default_on_delete_is_cascade(self):
        fk = ForeignKey(to="auth.User")
        assert fk.on_delete is CASCADE

    def test_db_constraint_true_by_default(self):
        fk = ForeignKey(to="auth.User")
        assert fk.db_constraint is True


class TestOneToOneField:
    def test_inherits_foreignkey(self):
        o2o = OneToOneField(to="auth.User", on_delete=CASCADE)
        assert o2o.to == "auth.User"
        assert o2o.on_delete is CASCADE


class TestManyToManyField:
    def test_basic(self):
        m2m = ManyToManyField(to="auth.User")
        assert m2m.to == "auth.User"
        assert m2m.symmetrical is True


class TestOnDeleteFunctions:
    def test_all_functions_exist(self):
        assert callable(CASCADE)
        assert callable(SET_NULL)
        assert callable(SET_DEFAULT)
        assert callable(PROTECT)
        assert callable(DO_NOTHING)
        assert callable(SET)

    def test_functions_are_plain(self):
        """Each function takes no args and returns None."""
        assert CASCADE() is None
        assert SET_NULL() is None
        assert SET_DEFAULT() is None
        assert PROTECT() is None
        assert DO_NOTHING() is None
        assert SET(42) is None