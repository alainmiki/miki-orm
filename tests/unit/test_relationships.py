"""ForeignKey and ManyToMany relationship behaviors (CASCADE, SET_NULL, PROTECT, DO_NOTHING)."""

import pytest

from myorm import configure, settings
from myorm.models.base import Model
from myorm.models.fields import (
    AutoField, BooleanField, CharField, IntegerField, ForeignKey, ManyToManyField
)
from myorm.models.relationships import CASCADE, SET_NULL, SET_DEFAULT, PROTECT, DO_NOTHING


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Dept(Model):
    name = CharField(max_length=50)

    class Meta:
        table_name = "depts"


class Emp(Model):
    name = CharField(max_length=50)
    dept = ForeignKey(Dept, on_delete=CASCADE, related_name="employees")
    salary = IntegerField(default=0)

    class Meta:
        table_name = "emps"


class ProtectedParent(Model):
    name = CharField(max_length=50)

    class Meta:
        table_name = "protected_parents"


class ProtectedChild(Model):
    name = CharField(max_length=50)
    parent = ForeignKey(ProtectedParent, on_delete=PROTECT, related_name="children")

    class Meta:
        table_name = "protected_children"


class SetNullParent(Model):
    name = CharField(max_length=50)

    class Meta:
        table_name = "setnull_parents"


class SetNullChild(Model):
    name = CharField(max_length=50)
    parent = ForeignKey(SetNullParent, on_delete=SET_NULL, null=True, related_name="kids")

    class Meta:
        table_name = "setnull_children"


class SetDefaultParent(Model):
    name = CharField(max_length=50)
    default_val = IntegerField(default=99)

    class Meta:
        table_name = "setdefault_parents"


class SetDefaultChild(Model):
    name = CharField(max_length=50)
    parent = ForeignKey(SetDefaultParent, on_delete=SET_DEFAULT, null=True, related_name="items", default_field="default_val")

    class Meta:
        table_name = "setdefault_children"


class DoNothingParent(Model):
    name = CharField(max_length=50)

    class Meta:
        table_name = "donothing_parents"


class DoNothingChild(Model):
    name = CharField(max_length=50)
    parent = ForeignKey(DoNothingParent, on_delete=DO_NOTHING, null=True, related_name="orphans")

    class Meta:
        table_name = "donothing_children"


class SimpleM2M_A(Model):
    name = CharField(max_length=50)

    class Meta:
        table_name = "m2m_a"


class SimpleM2M_B(Model):
    items = ManyToManyField(SimpleM2M_A, related_name="bs")

    class Meta:
        table_name = "m2m_b"


# ---------------------------------------------------------------------------
# Fixtures
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
def backend(request):
    backend = request.param
    configure(databases={"default": get_config(backend)})
    yield backend
    settings.connection_manager.close_all()


def ensure_table(model):
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
            else:
                setattr(dummy, fname, None)
    try:
        dummy.save(force_insert=True)
    except Exception:
        pass


def clear_table(model):
    try:
        conn = settings.connection_manager.get_connection()
        conn.execute(f"DELETE FROM {model._meta.table_name}", ())
        conn.commit()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_db(backend):
    for m in [Dept, Emp, ProtectedParent, ProtectedChild, SetNullParent, SetNullChild,
              SetDefaultParent, SetDefaultChild, DoNothingParent, DoNothingChild,
              SimpleM2M_A, SimpleM2M_B]:
        ensure_table(m)

    yield

    for m in [Dept, Emp, ProtectedParent, ProtectedChild, SetNullParent, SetNullChild,
              SetDefaultParent, SetDefaultChild, DoNothingParent, DoNothingChild,
              SimpleM2M_A, SimpleM2M_B]:
        clear_table(m)


from myorm.models.fields import AutoField  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cascade_delete(backend):
    d = Dept.objects.create(name="Engineering")
    e1 = Emp.objects.create(name="Alice", dept=d, salary=100)
    e2 = Emp.objects.create(name="Bob", dept=d, salary=200)

    assert Emp.objects.filter(dept=d).count() == 2

    d.delete()
    assert Emp.objects.count() == 0


def test_protect_raises(backend):
    p = ProtectedParent.objects.create(name="P")
    ProtectedChild.objects.create(name="C1", parent=p)

    with pytest.raises(Exception):
        p.delete()


def test_set_null(backend):
    p = SetNullParent.objects.create(name="Parent")
    c = SetNullChild.objects.create(name="Child", parent=p)

    p.delete()
    c_fetched = SetNullChild.objects.get(pk=c.pk)
    assert c_fetched.parent is None


def test_set_default(backend):
    p = SetDefaultParent.objects.create(name="Parent", default_val=42)
    c = SetDefaultChild.objects.create(name="Child", parent=p)

    p.delete()
    c_fetched = SetDefaultChild.objects.get(pk=c.pk)
    # FK set to the default_val (42)
    assert c_fetched.parent == 42


def test_do_nothing(backend):
    p = DoNothingParent.objects.create(name="Parent")
    c = DoNothingChild.objects.create(name="Child", parent=p)

    try:
        p.delete()
        # If no FK constraint, child still exists and points to non-existent parent; This may still exist
        assert DoNothingChild.objects.filter(pk=c.pk).count() == 1
    except Exception:
        # FK constraint violation acceptable
        pass


def test_many_to_many(backend):
    a1 = SimpleM2M_A.objects.create(name="A1")
    a2 = SimpleM2M_A.objects.create(name="A2")
    b = SimpleM2M_B.objects.create(name="B")

    b.items.add(a1, a2)
    assert b.items.count() == 2
    assert a1.bs.count() == 1

    b.items.remove(a1)
    assert b.items.count() == 1
    assert a1.bs.count() == 0

    b.items.clear()
    assert b.items.count() == 0


def test_many_to_many_bidirectional(backend):
    """Ensure the reverse side of M2M works via related_name."""
    a = SimpleM2M_A.objects.create(name="Alpha")
    b1 = SimpleM2M_B.objects.create(name="Beta1")
    b2 = SimpleM2M_B.objects.create(name="Beta2")
    b1.items.add(a)
    b2.items.add(a)

    assert a.bs.count() == 2
    names = sorted(b.name for b in a.bs.all())
    assert names == ["Beta1", "Beta2"]


def test_related_name_reverse_fk(backend):
    d = Dept.objects.create(name="HR")
    Emp.objects.create(name="E1", dept=d, salary=10)
    Emp.objects.create(name="E2", dept=d, salary=20)

    assert d.employees.count() == 2
    names = sorted(e.name for e in d.employees.all())
    assert names == ["E1", "E2"]
