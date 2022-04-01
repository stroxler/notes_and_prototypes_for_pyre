from __future__ import annotations

import ast
import dataclasses
from typing import (
    Any, Dict, Generic, Protocol, Set, Tuple, TypeVar, List, Optional, cast
)

from typing_extensions import TypeAlias
import textwrap
from collections import defaultdict


T = TypeVar("T")



class ReadOnlyEnv(Generic[T], Protocol):
    def __call__(self, key: str, dependency: str) -> T:
        ...


class Cache(Generic[T]):
    # It's a pain to type this well so I'll place fast and loose
    # with the types here to avoid an explosion of generics
    cached: Dict[str, T]  # object is the value type
    dependencies: Dict[str, Set[object]]  # object is the

    def __init__(self, cached: Optional[Dict[str, T]] = None) -> None:
        self.cached = cached if cached is not None else {}
        self.dependencies = defaultdict(lambda: set())


def module_for_key(key) -> str:
    return key.split(".")[0]


class EnvTable(Generic[T]):
    upstream_env: Optional[EnvTable]
    cache: Cache[T]
    overlay: Optional[Tuple[str, EnvTable[T]]]

    # Only needed to get clean dependency propagation; it's possible to make
    # this work without registering children if dependencies are passed around
    # externally, which we might do in ocaml.
    children: Dict[str, EnvTable[T]]

    def __init__(self, upstream_env=None, overlay=None) -> None:
        self.upstream_env = upstream_env
        self.overlay = overlay
        self.cache = Cache()
        self.children = {}

    @classmethod
    def new(
        cls,
        upstream_env: Optional[EnvTable],
        overlay: Tuple[str, EnvTable[T]],
        code: str,  # ignored in default implementation
    ) -> EnvTable[T]:
        return cls(overlay=overlay, upstream_env=upstream_env)

    @property
    def upstream_get(self) -> ReadOnlyEnv:
        if self.upstream_env is None:
            return ...  # typing this correctly is annoying and not illuminating
        else:
            return self.upstream_env.read_only()

    @staticmethod
    def produce_value(key: str, upstream_get: Any, current_env_getter: Any) -> T:
        "Must be implemented by child environments"
        raise NotImplementedError()

    @property
    def dependencies(self) -> Dict[str, Set[str]]:
        # Dependencies are global. This is a horrible horrible hack to make
        # it so - in ocaml this will happen automatically unless we do something
        # fancy to avoid it
        #
        # It's actually not strictly necessary to have global dependencies if we
        # do a pull-based update to initialize the overlay, but we do need them
        # if we want to do a push-based initial update.
        if self.overlay is None:
            return self.cache.dependencies
        else:
            return self.overlay[1].cache.dependencies


    def register_dependency(self, key: str, dependency: str) -> None:
        self.dependencies[key] = self.dependencies.get(key, set())
        self.dependencies[key].add(dependency)

    def get(self, key: str, dependency: str) -> T:

        # first check whether we own the key - do nothing at all if not!
        if self.overlay is not None:
            overlay_module, parent_env = self.overlay
            if module_for_key(key) != overlay_module:
                return parent_env.get(key, dependency)
        # otherwise, do exactly the same thing `factor_out_memory.py` did
        self.register_dependency(key, dependency)
        if key not in self.cache.cached:
            self.cache.cached[key] = self.produce_value(
                key,
                self.upstream_get,
                current_env_getter=self.cache.cached.get
            )
        return self.cache.cached[key]

    def update_for_push(
        self,
        keys_to_update: Set[str]
    ) -> Set[str]:
        overlay_module = (
            None
            if self.overlay is None
            else self.overlay[0]
        )
        downstream_deps = set()

        # update as before, if this module owns the key
        for key in keys_to_update:
            if overlay_module is None or module_for_key(key) == overlay_module:
                self.cache.cached[key] = self.produce_value(
                    key,
                    self.upstream_get,
                    current_env_getter=self.cache.cached.get
                )
                downstream_deps |= self.dependencies[key]

        # Propagate the dependencies to child environments as well, and track all
        # of those triggered dependencies as well. Note that we're
        # doing two inefficient things here:
        # - passing all triggers to all child environments, instead of filtering them
        #   down ahead of time. This will cause more trigger scanning, but not more
        #   "serious" computation.
        # - combining all of the triggered dependencies. This can actually cause
        #   more computation because the parent environment might have some unnecessary
        #   computation triggered by invalidations in a child. But it won't lead to
        #   inconsistency, and several heuristics suggest the effect should be small
        #   even if we use global dependencies and even smaller if dependencies are
        #   tracked per-overlay.
        #
        # It would be possible to do both things more efficiently by writing more
        # complex code in this python example, but it might be hard to implement in
        # prod and I think it's important to realize we can probably get away with
        # greedily triggering updates.
        for child in self.children.values():
            downstream_deps |= child.update_for_push(keys_to_update)

        return downstream_deps

    def create_overlay(self, module: str, code: str) -> EnvTable[T]:
        if self.upstream_env is None:
            upstream_overlay = None
        else:
            upstream_overlay = self.upstream_env.create_overlay(module, code)

        self.children[module] = self.new(
            upstream_env=upstream_overlay,
            overlay=(module, self),
            code=code,
        )
        return self.children[module]

    def get_overlay(self, module: str, code: str) -> EnvTable[T]:
        if module in self.children:
            print("using existing")
            child = self.children[module]
        else:
            print("creating new")
            child = self.create_overlay(module=module, code=code)
        if child.overlay is None:
            raise RuntimeError()
        return child

    def update(self, module: str, code: str, in_overlay: bool = False) -> Set[str]:
        if self.upstream_env is None:
            raise NotImplementedError()
        # switch to the child and update that. Note that upstream environments are
        # created via get_overlay, and so the update itself happens without `in_overlay`
        if in_overlay:
            child = self.get_overlay(module, code)
            keys_to_update = child.upstream_env.update(module, code)
            return child.update_for_push(keys_to_update)
        # update this stack (which will also update children)
        else:
            keys_to_update = self.upstream_env.update(module, code)
            return self.update_for_push(keys_to_update)

    def read_only(self) -> ReadOnlyEnv:
        return self.get


# "module_name"
Module: TypeAlias = str
Code: TypeAlias = str


class CodeEnv(EnvTable[Code]):

    def __init__(
        self,
        upstream_env=None,
        overlay=None,
        code: Optional[Dict[str, Code]] = None,
    ) -> None:
        super().__init__(upstream_env=None, overlay=overlay)
        self.cache.cached = code

    @classmethod
    def new(
        cls,
        upstream_env: Optional[EnvTable],
        overlay: Tuple[str, EnvTable[T]],
        code: str,
    ) -> EnvTable[T]:
        module, _ = overlay
        return cls(overlay=overlay, upstream_env=upstream_env, code={module: code})


    @staticmethod
    def produce_value(key: Module, upstream_get: Any, current_env_getter: Any) -> Code:
        return current_env_getter(key)


    def update(self, module: str, code: str, in_overlay: bool=False) -> Set[str]:
        # `CodeEnv` does not have an upstream environment. So, we have to
        # override the default `update` method to set the value before we
        # "produce" it. (This is what `basic.py` does too.)
        if in_overlay:
            raise RuntimeError("We should never directly be updating in overlay!")
        else:
            self.cache.cached[module] = code
            return cast(Set[str], self.dependencies[module])


class AstEnv(EnvTable[ast.AST]):

    @staticmethod
    def produce_value(key: Module, upstream_get: Any, current_env_getter: Any) -> ast.AST:
        code = upstream_get(key, dependency=key)
        return ast.parse(textwrap.dedent(code))


# "module_name.ClassName"
ClassName: TypeAlias = str


class ClassBodyEnv(EnvTable[ast.ClassDef]):

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.AST], current_env_getter: Any):
        module, relative_name = key.split(".")
        ast_ = upstream_get(key=module, dependency=key)
        # pyre-fixme[16]: `_ast.AST` has no attribute `body`.
        for class_def in ast_.body:
            if class_def.name == relative_name:
                return class_def


ClassAncestors: TypeAlias = List[str]


class ClassParentsEnv(EnvTable[ClassAncestors]):

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.ClassDef], current_env_getter: Any):
        class_def = upstream_get(key, dependency=key)
        return [
            ast.unparse(b)
            for b in class_def.bases
        ]


class ClassGrandparentsEnv(EnvTable[ClassAncestors]):


    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ClassAncestors], current_env_getter: Any):
        parents = upstream_get(key, dependency=key)
        return [
            grandparent
            for parent in parents
            for grandparent in upstream_get(parent, dependency=key)
        ]



def create_env_stack(code: Dict[str, str]) -> Tuple[
    CodeEnv,
    AstEnv,
    ClassBodyEnv,
    ClassParentsEnv,
    ClassGrandparentsEnv,
]:
    code_env = CodeEnv(code=code)
    ast_env = AstEnv(code_env)
    class_body_env = ClassBodyEnv(ast_env)
    class_parents_env = ClassParentsEnv(class_body_env)
    class_grandparents_env = ClassGrandparentsEnv(class_parents_env)
    return (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    )
