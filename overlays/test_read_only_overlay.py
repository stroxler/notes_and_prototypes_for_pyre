#!/usr/bin/env python3
import functools
from read_only_overlay import create_env_stack


def debug(f):
    @functools.wraps(f)
    def wrapper():
        try:
            f()
        except Exception:
            import pdb;
            import traceback
            import sys

            traceback.print_exc()
            _, _, tb = sys.exc_info()
            pdb.post_mortem(tb)

    return wrapper



@debug
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
    """)
    assert class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.Y"]



@debug
def test_overlay():
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

    class_grandparents_overlay_get = class_grandparents_env.overlay(
        module="b",
        code="""
            class Z(a.Y): pass
            class W(b.Z): pass
        """,
    )
    assert class_grandparents_overlay_get("b.Z", "") == ["a.X"]
    assert class_grandparents_overlay_get("b.W", "") == ["a.Y"]

    # the original env should still work
    assert class_grandparents_env.get("b.Z", "") == []
    assert class_grandparents_env.get("b.W", "") == ["a.X"]


    # Change and save module `a`.
    class_grandparents_env.update("a", code="""
        class X(a.Y): pass
        class Y: pass
    """)

    # The overlay reflects the newly-saved contents of `a`.
    assert class_grandparents_env.get("b.Z", "") == ["a.Y"]
    assert class_grandparents_env.get("b.W", "") == ["a.X"]

    assert class_grandparents_overlay_get("b.Z", "") == []
    assert class_grandparents_overlay_get("b.W", "") == ["a.Y"]
