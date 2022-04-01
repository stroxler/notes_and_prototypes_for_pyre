#!/usr/bin/env python3
from wrap_env import create_env_stack
import pytest


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
    """, in_overlay=False)
    assert class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.Y"]


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
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, in_overlay=True)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.children["b"].get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.W", "") == ["a.Y"]
    assert class_grandparents_env.get("c.ZChild", "") == ["a.X"]
    with pytest.raises(KeyError):
        class_grandparents_env.children["c"]

    print(class_grandparents_env)

    # Edit 2.
    class_grandparents_env.update("b", code= """
        class Z: pass
        class ZChild2(b.Z): pass
        class W(b.ZChild2): pass
    """, in_overlay=True)

    print(class_grandparents_env)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.children["b"].get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.W", "") == ["b.Z"]
    assert class_grandparents_env.children["b"].get("b.ZChild2", "") == []
    assert class_grandparents_env.get("c.ZChild", "") == ["a.X"]
    with pytest.raises(KeyError):
        class_grandparents_env.children["c"]


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

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, in_overlay=True)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.children["b"].get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.W", "") == ["a.Y"]

    # Change and save module `a`.
    class_grandparents_env.update("a", code="""
        class X(a.Y): pass
        class Y: pass
    """, in_overlay=False)

    # The wrapped environment reflects the newly-saved contents of `a`.
    assert class_grandparents_env.children["b"].get("b.Z", "") == []
    assert class_grandparents_env.children["b"].get("b.W", "") == ["a.Y"]

    # The original environment reflects the newly-saved contents of `a`.
    assert class_grandparents_env.get("b.Z", "") == ["a.Y"]
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

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(c.BrandNewDependent): pass
        class W(b.Z): pass
    """, in_overlay=True)

    assert class_grandparents_env.children["b"].get("b.Z", "") == []
    assert class_grandparents_env.children["b"].get("b.W", "") == ["c.BrandNewDependent"]

    # Change and save module `c`.
    class_grandparents_env.update("c", code="""
        class BrandNewDependent(a.X): pass
    """, in_overlay=False)

    # The wrapped environment reflects the change in `BrandNewDependent` even
    # though the saved version of `b` didn't have BrandNewDependent as a
    # dependent.
    assert class_grandparents_env.children["b"].get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.W", "") == ["c.BrandNewDependent"]


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

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, in_overlay=True)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    # Dependency ZChild should not be updated. It should reflect the saved
    # contents of `b`.
    assert class_grandparents_env.get("c.ZChild", "") == ["a.X"]

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
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, in_overlay=True)

    assert class_grandparents_env.children["b"].get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.W", "") == ["a.Y"]

    # We have not called `get("c.ZChild")` before, so it is not
    # in cache. When we `produce_value` using its dependents, such as `Z`, we
    # should use their saved-file values, not unsaved-file values.
    assert class_grandparents_env.get("c.ZChild", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("c.ZChild", "") == ["a.X"]

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
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    # Edit 1.
    class_grandparents_env.update("b", code= """
        class Z(a.Y): pass
        class W(b.Z): pass
    """, in_overlay=True)

    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.children["b"].get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.W", "") == ["a.Y"]

    class_grandparents_env.update("b", code="""
        class Z(b.W): pass
        class W(a.X): pass
    """, in_overlay=False)

    assert class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.children["b"].get("b.Z", "") == ["a.X"]
    # Note: this differs from test_wrap_memory.py because here we don't
    # clear the overlay when new changes are saved (editor state is not assumed
    # to be in sync)
    assert class_grandparents_env.get("b.W", "") == []
    assert class_grandparents_env.children["b"].get("b.W", "") == ["a.Y"]



def test_edge_case__now_fixed() -> None:
    def set_up():
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
                class B0(a.X): pass
                class B1(a.Y): pass
            """,
        })

        # create some dependencies; this isn't actually important, it's just needed
        # because the code isn't very robust
        class_grandparents_env.get("b.B0", "")

        # Trigger a pair of updates
        class_grandparents_env.update("a", code="""
            class X: pass
            class Y: pass
        """, in_overlay=True)

        return class_grandparents_env

    class_grandparents_env = set_up()
    # we get the same results...
    assert class_grandparents_env.get("b.B1", "") == ["a.X"]
    with pytest.raises(KeyError):
        class_grandparents_env.children["b"]

    class_grandparents_env = set_up()
    # ... regardless of the order in which we call `get`
    assert class_grandparents_env.get("b.B1", "") == ["a.X"]
    with pytest.raises(KeyError):
        class_grandparents_env.children["b"]
