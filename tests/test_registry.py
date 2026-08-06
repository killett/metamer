import pytest

from metamer.core.registry import (
    REGISTRY_VERSION,
    DuplicateRegistrationError,
    kernel_registry,
    recipe_registry,
)


def test_registry_version_is_recorded():
    """REGISTRY_VERSION exists and is a non-empty string.

    Bug this catches: shipping without a version stamp, so "matern32" could
    change meaning between releases and silently invalidate a cached run.
    """
    assert isinstance(REGISTRY_VERSION, str)
    assert REGISTRY_VERSION


def test_kernel_and_recipe_registries_are_distinct():
    """Kernels and recipes do not share a namespace.

    Bug this catches: putting 'hw2010_ar5' in the kernel registry, which
    bundles a noise model with a signal model, an engine, and a criterion and
    makes the return type of a lookup unpredictable.
    """
    assert kernel_registry is not recipe_registry
    # Task 4 retyped kernel_registry as Registry[Callable[..., Family]]. These
    # probes deliberately register non-families: what is under test is the
    # namespace mechanics, not family conformance, and a probe that satisfied
    # the whole Family protocol would stop being a throwaway.
    kernel_registry.register("dummy_kernel_probe")(lambda: "kernel")  # type: ignore[arg-type,return-value]
    assert "dummy_kernel_probe" not in recipe_registry
    kernel_registry.unregister("dummy_kernel_probe")


def test_duplicate_registration_raises():
    """Registering the same key twice is an error, not an overwrite.

    Bug this catches: two plugins claiming 'matern32', where last-import-wins
    would change results depending on import order.
    """
    # Non-family probes, as above: duplicate detection is registry mechanics.
    kernel_registry.register("dup_probe")(lambda: 1)  # type: ignore[arg-type,return-value]
    with pytest.raises(DuplicateRegistrationError, match="dup_probe"):
        kernel_registry.register("dup_probe")(lambda: 2)  # type: ignore[arg-type,return-value]
    kernel_registry.unregister("dup_probe")
