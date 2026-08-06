"""Two separate registries: kernel families, and experiment recipes.

Recipes bundle a noise model with a signal model, an engine, and a criterion.
They are not kernels, and keeping them apart is what stops the kernel registry
becoming a junk drawer with an unpredictable lookup type.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Import-time cycle, resolved by deferring this to type-check time only.
    # `registry` -> `families.base` drags in the `families` *package* __init__,
    # which imports `white` and `matern12`, which import `kernel_registry` back
    # out of this module while it is still executing:
    #   ImportError: cannot import name 'kernel_registry' from partially
    #   initialized module 'metamer.core.registry'
    # `from __future__ import annotations` above keeps the annotation on
    # `kernel_registry` unevaluated at runtime, so the deferred import is
    # enough -- the registry never needs `Family` as a runtime object.
    from metamer.core.families.base import Family

REGISTRY_VERSION = "1"
"""Stamped into provenance so a name cannot silently change meaning."""


class DuplicateRegistrationError(KeyError):
    """A key was registered twice."""


class Registry[T]:
    """A name-to-factory registry with decorator registration."""

    def __init__(self, name: str, entry_point_group: str | None = None) -> None:
        """Create an empty registry.

        Args:
            name: Human-readable registry name, used in error messages.
            entry_point_group: Optional entry-point group to lazily load
                registrations from on first lookup.
        """
        self._name = name
        self._entry_point_group = entry_point_group
        self._items: dict[str, T] = {}
        self._loaded_entry_points = False

    def register(self, key: str) -> Callable[[T], T]:
        """Return a decorator registering a factory under `key`.

        Args:
            key: Registry name.

        Returns:
            A decorator that registers and returns its argument unchanged.

        Raises:
            DuplicateRegistrationError: If `key` is already registered.
        """

        def decorator(item: T) -> T:
            if key in self._items:
                raise DuplicateRegistrationError(
                    f"{self._name}: {key!r} is already registered"
                )
            self._items[key] = item
            return item

        return decorator

    def unregister(self, key: str) -> None:
        """Remove a key. Used by tests; not part of the public contract."""
        self._items.pop(key, None)

    def _load_entry_points(self) -> None:
        """Load registrations from the configured entry-point group, once."""
        if self._loaded_entry_points or self._entry_point_group is None:
            return
        group = self._entry_point_group
        self._loaded_entry_points = True
        for ep in entry_points(group=group):
            if ep.name not in self._items:
                self._items[ep.name] = ep.load()

    def __getitem__(self, key: str) -> T:
        """Look up `key`, loading entry points first if configured.

        Raises:
            KeyError: If `key` is not registered.
        """
        self._load_entry_points()
        if key not in self._items:
            available = ", ".join(sorted(self._items))
            raise KeyError(f"{self._name}: unknown key {key!r}. Available: {available}")
        return self._items[key]

    def __contains__(self, key: str) -> bool:
        """Return whether `key` is registered."""
        self._load_entry_points()
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        """Iterate registered keys in sorted order."""
        self._load_entry_points()
        return iter(sorted(self._items))


kernel_registry: Registry[Callable[..., Family]] = Registry(
    "kernel_registry", entry_point_group="metamer.kernels"
)
recipe_registry: Registry[Callable[..., object]] = Registry("recipe_registry")
