"""Base manager class for query and persistence APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .queryset import QuerySet

from ..models.base import Model


class Manager:
    """Default manager exposing Django-like query methods.

    Each model class gets a Manager instance attached as ``objects``
    by the metaclass.

    Users can define custom managers by subclassing Manager and
    assigning an instance to a class attribute on their model.
    """

    model: type[Model]

    def __init__(self, model: type[Model]) -> None:
        self.model = model

    def all(self) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model)

    def filter(self, *args: Any, **kwargs: Any) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).filter(*args, **kwargs)

    def exclude(self, *args: Any, **kwargs: Any) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).exclude(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Model:
        from .queryset import QuerySet

        return QuerySet(self.model).get(*args, **kwargs)

    def get_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Model, bool]:
        from .queryset import QuerySet

        return QuerySet(self.model).get_or_create(defaults=defaults, **kwargs)

    def get_object_or_404(self, *args: Any, **kwargs: Any) -> Model:
        from .queryset import QuerySet

        try:
            return QuerySet(self.model).get(*args, **kwargs)
        except Exception:
            from ..models.base import ObjectDoesNotExist

            raise ObjectDoesNotExist(
                f"{self.model.__name__} matching query does not exist."
            )

    def create(self, **kwargs: Any) -> Model:
        obj = self.model(**kwargs)
        obj.save()
        return obj

    def first(self) -> Model | None:
        from .queryset import QuerySet

        return QuerySet(self.model).first()

    def last(self) -> Model | None:
        from .queryset import QuerySet

        return QuerySet(self.model).last()

    def count(self) -> int:
        from .queryset import QuerySet

        return QuerySet(self.model).count()

    def exists(self) -> bool:
        from .queryset import QuerySet

        return QuerySet(self.model).exists()

    def update_or_create(
        self, defaults: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[Model, bool]:
        from .queryset import QuerySet

        return QuerySet(self.model).update_or_create(defaults=defaults, **kwargs)

    def bulk_create(self, objs: list[Model], batch_size: int = 1000) -> list[Model]:
        for obj in objs:
            obj.save()
        return objs

    def update(self, **values: Any) -> int:
        from .queryset import QuerySet

        return QuerySet(self.model).update(**values)

    def values(self, *fields: str) -> list[dict[str, Any]]:
        from .queryset import QuerySet

        return QuerySet(self.model).values(*fields)

    def values_list(self, *fields: str) -> list[tuple[Any, ...]]:
        from .queryset import QuerySet

        return QuerySet(self.model).values_list(*fields)

    def select_related(self, *related: str) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).select_related(*related)

    def prefetch_related(self, *related: str) -> "QuerySet":
        from .queryset import QuerySet

        return QuerySet(self.model).prefetch_related(*related)

    def distinct(self, *fields: str) -> "QuerySet":
        """Return distinct results."""
        from .queryset import QuerySet

        return QuerySet(self.model).distinct(*fields)

    def none(self) -> "QuerySet":
        """Return an empty QuerySet."""
        from .queryset import QuerySet

        return QuerySet(self.model).none()

    def annotate(self, **annotations: Any) -> "QuerySet":
        """Add computed fields via aggregation."""
        from .queryset import QuerySet

        return QuerySet(self.model).annotate(**annotations)

    def aggregate(self, **aggregates: Any) -> dict[str, Any]:
        """Return aggregation result as dictionary."""
        from .queryset import QuerySet

        return QuerySet(self.model).aggregate(**aggregates)

    def only(self, *fields: str) -> "QuerySet":
        """Select only specified fields."""
        from .queryset import QuerySet

        return QuerySet(self.model).only(*fields)

    def defer(self, *fields: str) -> "QuerySet":
        """Exclude specified fields from selection."""
        from .queryset import QuerySet

        return QuerySet(self.model).defer(*fields)

    def in_bulk(self, id_list: list[Any] | None = None, *, field_name: str = "pk") -> dict[Any, Model]:
        """Return a dictionary mapping field_name values to model instances."""
        from .queryset import QuerySet

        return QuerySet(self.model).in_bulk(id_list, field_name=field_name)

    def union(self, *querysets: "QuerySet", all: bool = False) -> "QuerySet":
        """Return union of this QuerySet with other QuerySets."""
        from .queryset import QuerySet

        return QuerySet(self.model).union(*querysets, all=all)

    def intersection(self, *querysets: "QuerySet") -> "QuerySet":
        """Return intersection of this QuerySet with other QuerySets."""
        from .queryset import QuerySet

        return QuerySet(self.model).intersection(*querysets)

    def difference(self, *querysets: "QuerySet") -> "QuerySet":
        """Return difference of this QuerySet with other QuerySets."""
        from .queryset import QuerySet

        return QuerySet(self.model).difference(*querysets)

    def having(self, *args: Any, **kwargs: Any) -> "QuerySet":
        """Filter on aggregated values (must be used with annotate())."""
        from .queryset import QuerySet

        return QuerySet(self.model).having(*args, **kwargs)

    async def async_all(self, connection: Any = None) -> list[Model]:
        """Return all objects asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.all()

    async def async_filter(self, *args: Any, connection: Any = None, **kwargs: Any) -> list[Model]:
        """Filter objects asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection).filter(*args, **kwargs)
        return await qs.all()

    async def async_get(self, *args: Any, connection: Any = None, **kwargs: Any) -> Model:
        """Get a single object asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection).filter(*args, **kwargs)
        return await qs.get()

    async def async_first(self, connection: Any = None) -> Model | None:
        """Return first object or None asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.first()

    async def async_last(self, connection: Any = None) -> Model | None:
        """Return last object or None asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.last()

    async def async_count(self, connection: Any = None) -> int:
        """Count objects asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.count()

    async def async_exists(self, connection: Any = None) -> bool:
        """Check if any objects exist asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.exists()

    async def async_create(self, connection: Any = None, **kwargs: Any) -> Model:
        """Create and save a new object asynchronously."""
        # This needs async object creation; defer to model async_save
        obj = self.model(**kwargs)
        await obj.async_save(connection=connection)
        return obj

    async def async_get_or_create(
        self, defaults: dict[str, Any] | None = None, connection: Any = None, **kwargs: Any
    ) -> tuple[Model, bool]:
        """Get or create object asynchronously (stub)."""
        raise NotImplementedError("async_get_or_create not yet implemented")

    async def async_update(self, connection: Any = None, **values: Any) -> int:
        """Update all matching objects asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.update(**values)

    async def async_values(self, *fields: str, connection: Any = None) -> list[dict[str, Any]]:
        """Return values as dictionaries asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.values(*fields)

    async def async_values_list(self, *fields: str, connection: Any = None) -> list[tuple[Any, ...]]:
        """Return values as tuples asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection)
        return await qs.values_list(*fields)

    async def async_select_related(self, *related: str, connection: Any = None) -> list[Model]:
        """Fetch related objects in a single query asynchronously."""
        from .async_queryset import AsyncQuerySet
        qs = AsyncQuerySet(self.model, connection=connection).select_related(*related)
        return await qs.all()


class ManagerDescriptor:
    """Descriptor that returns the Manager instance for a model class.

    This allows ``MyModel.objects`` to return a Manager rather than a
    bound method, while still allowing custom managers to be defined.
    """

    def __get__(self, obj: Any, cls: type[Model] | None = None) -> Manager:
        if cls is None:
            raise AttributeError("Manager must be accessed via a model class.")
        # If the class defined its own manager as a class attribute,
        # return that (supports custom managers).
        for attr_name in dir(cls):
            attr = cls.__dict__.get(attr_name)
            if isinstance(attr, Manager) and attr_name != "_default_manager":
                return attr
        # Otherwise return the default manager stored by the metaclass
        if hasattr(cls, "_default_manager"):
            return cls._default_manager
        raise AttributeError(f"{cls.__name__} has no manager.")

    def __set__(self, obj: Any, value: Any) -> None:
        raise AttributeError("Cannot assign to 'objects' directly.")