"""QuerySet: filters, excludes, ordering, slicing, aggregation, get, get_or_create, update, delete, values/values_list."""

import pytest

from mikiorm.models.fields import AutoField, BooleanField  # noqa: E402
from mikiorm.models.base import Model
from mikiorm.models.fields import CharField, IntegerField, ForeignKey
from mikiorm.models.relationships import CASCADE


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Author(Model):
    name = CharField(max_length=50)
    email = CharField(max_length=100, unique=True)
    age = IntegerField(null=True)

    class Meta:
        table_name = "authors"


class Post(Model):
    title = CharField(max_length=100)
    slug = CharField(max_length=100, unique=True)
    author = ForeignKey(Author, on_delete=CASCADE, related_name="posts")
    views = IntegerField(default=0)
    status = CharField(max_length=10, choices=[("draft", "Draft"), ("pub", "Published")])

    class Meta:
        table_name = "posts"


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
    for m in [Author, Post]:
        ensure_table(m)

    yield

    for m in [Author, Post]:
        clear_table(m)


from mikiorm.models.fields import AutoField, BooleanField  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_and_get(backend):
    a = Author.objects.create(name="Alice", email="alice@example.com", age=30)
    fetched = Author.objects.get(pk=a.pk)
    assert fetched.name == "Alice"
    assert fetched.email == "alice@example.com"
    assert fetched.age == 30


def test_count_exists(backend):
    assert Author.objects.count() == 0
    Author.objects.create(name="Bob", email="bob@example.com")
    assert Author.objects.count() == 1
    assert Author.objects.filter(name="Bob").exists() is True
    assert Author.objects.filter(name="Missing").exists() is False


def test_first_last(backend):
    Author.objects.create(name="First", email="first@example.com")
    Author.objects.create(name="Last", email="last@example.com")
    assert Author.objects.order_by("id").first().name == "First"
    assert Author.objects.order_by("id").last().name == "Last"


def test_filter_exclude(backend):
    Author.objects.create(name="Alice", email="alice@example.com", age=25)
    Author.objects.create(name="Bob", email="bob@example.com", age=30)
    Author.objects.create(name="Charlie", email="charlie@example.com", age=25)

    results = Author.objects.filter(age=25).all()
    assert len(results) == 2

    results2 = Author.objects.exclude(name="Alice").all()
    assert len(results2) == 2


def test_filter_lookups(backend):
    for i in range(5):
        Author.objects.create(name=f"User{i}", email=f"u{i}@example.com", age=20 + i)

    assert Author.objects.filter(age__gt=22).count() == 3
    assert Author.objects.filter(age__gte=22).count() == 4
    assert Author.objects.filter(age__lt=22).count() == 2
    assert Author.objects.filter(age__lte=22).count() == 3
    assert Author.objects.filter(age__in=[21, 22, 23]).count() == 3
    assert Author.objects.filter(name__contains="2").count() >= 1
    assert Author.objects.filter(name__startswith="U").count() == 5
    assert Author.objects.filter(name__endswith="3").count() >= 1


def test_order_by(backend):
    for i in range(5):
        Author.objects.create(name=f"User{i}", email=f"u{i}@example.com", age=20 + i)

    asc = [a.name for a in Author.objects.order_by("name").all()]
    assert asc == sorted(asc)

    desc = [a.name for a in Author.objects.order_by("-name").all()]
    assert desc == sorted(desc, reverse=True)


def test_get_or_create(backend):
    obj, created = Author.objects.get_or_create(email="unique@example.com", defaults={"name": "New", "age": 40})
    assert created is True
    assert obj.name == "New"
    assert obj.age == 40

    obj2, created2 = Author.objects.get_or_create(email="unique@example.com", defaults={"name": "Changed"})
    assert created2 is False
    assert obj2.name == "New"


def test_update_or_create(backend):
    obj, created = Author.objects.update_or_create(email="up@example.com", defaults={"name": "Init", "age": 20})
    assert created is True
    obj2, updated = Author.objects.update_or_create(email="up@example.com", defaults={"name": "Changed", "age": 25})
    assert updated is False
    assert obj2.name == "Changed"
    assert obj2.age == 25


def test_bulk_create(backend):
    objs = [Author(name=f"Bulk{i}", email=f"b{i}@example.com") for i in range(10)]
    saved = Author.objects.bulk_create(objs)
    assert len(saved) >= 10
    assert Author.objects.count() >= 10


def test_values(backend):
    Author.objects.create(name="Vance", email="vance@example.com")
    result = Author.objects.values("name", "email")
    assert isinstance(result[0], dict)
    assert result[0]["name"] == "Vance"


def test_values_list(backend):
    Author.objects.create(name="Vance", email="vance@example.com")
    tuples = Author.objects.values_list("name", "email")
    assert ("Vance", "vance@example.com") in tuples
    flat = Author.objects.values_list("name", flat=True)
    assert "Vance" in flat


def test_update(backend):
    a = Author.objects.create(name="Ivy", email="ivy@example.com", age=20)
    affected = Author.objects.filter(pk=a.pk).update(age=30)
    assert affected == 1
    updated = Author.objects.get(pk=a.pk)
    assert updated.age == 30


def test_delete_query(backend):
    Author.objects.create(name="Jack", email="jack@example.com")
    Author.objects.create(name="Jill", email="jill@example.com")
    assert Author.objects.count() == 2
    deleted = Author.objects.filter(name__startswith="J").delete()
    assert deleted >= 2
    assert Author.objects.count() == 0


def test_get_object_or_404(backend):
    a = Author.objects.create(name="Found", email="found@example.com")
    result = Author.objects.get_object_or_404(pk=a.pk)
    assert result.name == "Found"
    with pytest.raises(Exception):
        Author.objects.get_object_or_404(pk=9999)


def test_select_related_stub(backend):
    author = Author.objects.create(name="S", email="s@example.com")
    Post.objects.create(title="P", slug="p", author=author, status="draft")
    # select_related should return a QuerySet; actual join is not yet implemented
    qs = Post.objects.select_related("author")
    assert hasattr(qs, "all")


def test_prefetch_related_stub(backend):
    author = Author.objects.create(name="P", email="p@example.com")
    Post.objects.create(title="Post1", slug="p1", author=author, status="draft")
    qs = Post.objects.prefetch_related("author")
    assert hasattr(qs, "all")
