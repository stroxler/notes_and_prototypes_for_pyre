#!/usr/bin/env python3
from existing import create_env_stack


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
