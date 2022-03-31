#!/usr/bin/env python3
from wrap_memory import create_env_stack


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
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

    class_grandparents_env.update("b", code="""
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=True)
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.Y"]


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
        "c": """
            class ZChild(b.Z): pass
        """,
    })


    # Do a couple of `get`s so that dependencies are set. Our toy program
    # crashes if dependencies are not found for a module.
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["a.Y"]
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=True) == ["a.X"]
    # This will still reflect the old saved content because we never modify
    # saved modules based on unsaved modules.
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=False) == ["a.X"]

    print(class_grandparents_env)

    # Edit 2.
    class_grandparents_env.update("b", code= """
        class Z: pass
        class ZChild2(b.Z): pass
        class W(b.ZChild2): pass
    """, is_saved_content=False)

    print(class_grandparents_env)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["b.Z"]
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.ZChild2", "", use_saved_contents_of_dependents=False) == []


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
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["a.Y"]

    # Change and save module `a`.
    class_grandparents_env.update("a", code="""
        class X(a.Y): pass
        class Y: pass
    """, is_saved_content=True)

    # The wrapped environment reflects the newly-saved contents of `a`.
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["a.Y"]

    # The original environment reflects the newly-saved contents of `a`.
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == ["a.Y"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

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
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(c.BrandNewDependent): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["c.BrandNewDependent"]

    # Change and save module `c`.
    class_grandparents_env.update("c", code="""
        class BrandNewDependent(a.X): pass
    """, is_saved_content=True)

    # The wrapped environment reflects the change in `BrandNewDependent` even
    # though the saved version of `b` didn't have BrandNewDependent as a
    # dependent.
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["c.BrandNewDependent"]


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
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=True) == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]
    # Dependency ZChild should not be updated. It should reflect the saved
    # contents of `b`.
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=True) == ["a.X"]

def test_get_uncached_dependent_of_unsaved_file():
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
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["a.Y"]

    # We have not called `get("c.ZChild")` before, so it is not
    # in cache. When we `produce_value` using its dependents, such as `Z`, we
    # should use their saved-file values, not unsaved-file values.
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("c.ZChild", "", use_saved_contents_of_dependents=False) == ["a.X"]

def test_save_edited_file() -> None:
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
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, is_saved_content=False)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == ["a.Y"]

    class_grandparents_env.update("b", code="""
        class Z(b.W): pass
        class W(a.X): pass
    """, is_saved_content=True)

    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=True) == ["a.X"]
    assert class_grandparents_env.get("b.Z", "", use_saved_contents_of_dependents=False) == ["a.X"]
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=True) == []
    assert class_grandparents_env.get("b.W", "", use_saved_contents_of_dependents=False) == []
