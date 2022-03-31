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
    """)
    assert class_grandparents_env.get("b.Z", "") == ["a.X"]
    assert class_grandparents_env.get("b.W", "") == ["a.Y"]




def test_wrap_memory() -> None:
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

    # TODO(pradeep): Add the overlay test.

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
