#!/usr/bin/env python3
import functools
from wrap_memory import create_env_stack, CachedTable, DictionaryCachedTable, WrappedCacheTable


def test_env_stack():
    (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    ) = create_env_stack(code={
        "a": """
            class X: pass
            class Y(a.X): pass
        """,
        "b": """
            class Z(a.X): pass
            class W(b.Z): pass
        """,
    })
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    class_grandparents_env.update("b", code="""
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=True)
    assert class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.Y"]


def test_wrapped_cache_table() -> None:
    original_cache_table: CachedTable = DictionaryCachedTable({"a.X": "value for a.X", "b.Y": "value for b.Y"})
    wrapped_cache_table: CachedTable = WrappedCacheTable(
        original_cache_table,
        overridden_module="a",
        overridden_cache_table=DictionaryCachedTable({"a.X": "new value for a.X"}),
    )

    assert wrapped_cache_table.has_key_in_cache("a.X")
    assert wrapped_cache_table.has_key_in_cache("b.Y")
    assert not wrapped_cache_table.has_key_in_cache("a.non_existent")

    assert wrapped_cache_table.look_up_key_in_cache("a.X") == "new value for a.X"
    assert wrapped_cache_table.look_up_key_in_cache("b.Y") == "value for b.Y"

    wrapped_cache_table.set_key_in_cache("a.X2", "value for a.X2")
    wrapped_cache_table.set_key_in_cache("b.Y", "new value for b.Y")

    assert wrapped_cache_table.look_up_key_in_cache("a.X") == "new value for a.X"
    assert wrapped_cache_table.look_up_key_in_cache("a.X2") == "value for a.X2"
    assert wrapped_cache_table.look_up_key_in_cache("b.Y") == "new value for b.Y"
    assert original_cache_table.look_up_key_in_cache("b.Y") == "new value for b.Y"

    original_cache_table.set_key_in_cache("b.Y", "original cache - new value for b.Y")

    assert wrapped_cache_table.look_up_key_in_cache("b.Y") == "original cache - new value for b.Y"


def test_with_wrapped_cache_table() -> None:
    (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    ) = create_env_stack(code={
        "a": """
            class X: pass
            class Y(a.X): pass
        """,
        "b": """
            class Z(a.X): pass
            class W(b.Z): pass
        """,
    })


    # Do a couple of `get`s so that dependencies are set. Our toy program
    # crashes if dependencies are not found for a module.
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    wrapped_class_grandparents_env = class_grandparents_env.with_wrapped_cache_table(overridden_module="b")

    # Edit 1.
    wrapped_class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    assert wrapped_class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert wrapped_class_grandparents_env.get("b.W", "") == ["a.Y"]

    # Edit 2.
    wrapped_class_grandparents_env.update("b", code= """
        class Z: pass
        class ZChild(b.Z): pass
        class W(b.ZChild): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    assert wrapped_class_grandparents_env.get("b.Z", "") == []
    assert wrapped_class_grandparents_env.get("b.W", "") == ["b.Z"]
    assert wrapped_class_grandparents_env.get("b.ZChild", "") == []


def test_save_other_file() -> None:
    (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    ) = create_env_stack(code={
        "a": """
            class X: pass
            class Y(a.X): pass
        """,
        "b": """
            class Z(a.X): pass
            class W(b.Z): pass
        """,
    })


    # Do a couple of `get`s so that dependencies are set. Our toy program
    # crashes if dependencies are not found for a module.
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    wrapped_class_grandparents_env = class_grandparents_env.with_wrapped_cache_table(overridden_module="b")

    # Edit 1.
    wrapped_class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    assert wrapped_class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert wrapped_class_grandparents_env.get("b.W", "") == ["a.Y"]

    # Change and save module `a`.
    wrapped_class_grandparents_env.update("a", code="""
        class X(a.Y): pass
        class Y: pass
    """, is_saved_content=True)

    # The wrapped environment reflects the newly-saved contents of `a`.
    assert wrapped_class_grandparents_env.get("b.Z", "") == []
    assert wrapped_class_grandparents_env.get("b.W", "") == ["a.Y"]

    # The original environment reflects the newly-saved contents of `a`.
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

def test_reflect_changes_in_brand_new_dependents() -> None:
    (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    ) = create_env_stack(code={
        "a": """
            class X: pass
            class Y(a.X): pass
        """,
        "b": """
            class Z(a.X): pass
            class W(b.Z): pass
        """,
        "c": """
            class BrandNewDependent: pass
        """,
    })


    # Do a couple of `get`s so that dependencies are set. Our toy program
    # crashes if dependencies are not found for a module.
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    wrapped_class_grandparents_env = class_grandparents_env.with_wrapped_cache_table(overridden_module="b")

    # Edit 1.
    wrapped_class_grandparents_env.update("b", code= """
        class Z(c.BrandNewDependent): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert wrapped_class_grandparents_env.get("b.Z", "") == []
    assert wrapped_class_grandparents_env.get("b.W", "") == ["c.BrandNewDependent"]

    # Change and save module `c`.
    wrapped_class_grandparents_env.update("c", code="""
        class BrandNewDependent(a.X): pass
    """, is_saved_content=True)

    # The wrapped environment reflects the change in `BrandNewDependent` even
    # though the saved version of `b` didn't have BrandNewDependent as a
    # dependent.
    assert wrapped_class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert wrapped_class_grandparents_env.get("b.W", "") == ["c.BrandNewDependent"]


def test_do_not_update_other_dependencies() -> None:
    (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    ) = create_env_stack(code={
        "a": """
            class X: pass
            class Y(a.X): pass
        """,
        "b": """
            class Z(a.X): pass
            class W(b.Z): pass
        """,
        "c": """
            class ZChild(b.Z): pass
        """,
    })


    # Do a couple of `get`s so that dependencies are set. Our toy program
    # crashes if dependencies are not found for a module.
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    assert class_grandparents_env.get("c.ZChild", "") == ["a.X"]

    wrapped_class_grandparents_env = class_grandparents_env.with_wrapped_cache_table(overridden_module="b")

    # Edit 1.
    wrapped_class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    # Dependency ZChild should not be updated. It should reflect the saved
    # contents of `b`.
    assert class_grandparents_env.get("c.ZChild", "") == ["a.X"]
