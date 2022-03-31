import ast
import dataclasses
from typing import (
    Any, Callable, Dict, Generic, Literal, Protocol, Set, Tuple, TypeVar, List, Optional, cast
)
from abc import abstractmethod

from typing_extensions import TypeAlias
import textwrap


T = TypeVar("T")



class ReadOnlyEnv(Generic[T], Protocol):
    def __call__(self, key: str, dependency: str) -> T:
        ...


@dataclasses.dataclass
class CachedTable(Generic[T]):
    _cached: Dict[str, T]

    def has_key_in_cache(self, key: str) -> bool:
        return key in self._cached

    def set_key_in_cache(self, key: str, value: T) -> None:
        self._cached[key] = value

    def look_up_key_in_cache(self, key: str) -> T:
        return self._cached[key]

@dataclasses.dataclass
class WritableEnv(Generic[T]):
    # This is only initialized globally. So, it basically stands in for Pyre's shared memory table.


    # It's a pain to type this well so I'll place fast and loose
    # with the types here to avoid an explosion of generics
    saved_contents_cache_table: CachedTable[T] = dataclasses.field(default_factory=lambda: CachedTable({}))
    unsaved_contents_cache_table: CachedTable[T] = dataclasses.field(default_factory=lambda: CachedTable({}))
    unsaved_modules: Set[str] = dataclasses.field(default_factory=set)
    dependencies: Dict[str, Set[object]] = dataclasses.field(default_factory=dict)


def module(key: str) -> str:
    return key.split(".")[0]

@dataclasses.dataclass
class EnvTable(Generic[T]):
    writable_env: WritableEnv[T]
    upstream_env: Optional["EnvTable"] = None

    def upstream_get(self, use_saved_contents_of_dependents: bool) -> ReadOnlyEnv:
        if self.upstream_env is None:
            return ...  # typing this correctly is annoying and not illuminating
        else:
            return self.upstream_env.read_only(use_saved_contents_of_dependents)

    @staticmethod
    def produce_value(key: str, upstream_get: Any, current_env_getter: Any) -> T:
        "Must be implemented by child environments"
        raise NotImplementedError()

    def register_dependency(self, key: str, dependency: str) -> None:
        self.writable_env.dependencies[key] = self.writable_env.dependencies.get(key, set())
        self.writable_env.dependencies[key].add(dependency)

    def get(self, key: str, dependency: str, use_saved_contents_of_dependents: bool) -> T:
        self.register_dependency(key, dependency)

        if use_saved_contents_of_dependents or module(key) not in self.writable_env.unsaved_modules:
            # Update the saved_contents_cache_table whether the module is
            # saved or unsaved.
            target_cache_table = self.writable_env.saved_contents_cache_table
            if not target_cache_table.has_key_in_cache(key):
                target_cache_table.set_key_in_cache(key, self.produce_value(
                    key,
                    self.upstream_get(use_saved_contents_of_dependents),
                    current_env_getter=target_cache_table.look_up_key_in_cache
                ))

            return target_cache_table.look_up_key_in_cache(key)

        target_cache_table = self.writable_env.unsaved_contents_cache_table

        if not target_cache_table.has_key_in_cache(key):
            target_cache_table.set_key_in_cache(key, self.produce_value(
                key,
                self.upstream_get(use_saved_contents_of_dependents),
                current_env_getter=target_cache_table.look_up_key_in_cache
            ))
        return target_cache_table.look_up_key_in_cache(key)

    def update_for_push(self, keys_to_update: Set[str], is_saved_content: bool) -> Set[str]:
        downstream_deps = set()

        for key in keys_to_update:
            is_unsaved_module = module(key) in self.writable_env.unsaved_modules

            if is_saved_content:
                # Update saved_contents_cache_table whether the module is saved or unsaved.
                target_cache_table = self.writable_env.saved_contents_cache_table
                target_cache_table.set_key_in_cache(key, self.produce_value(
                    key,
                    self.upstream_get(use_saved_contents_of_dependents=True),
                    current_env_getter=target_cache_table.look_up_key_in_cache
                ))
                downstream_deps |= self.writable_env.dependencies.get(key, set())

                # If the module is unsaved, also update
                # unsaved_contents_cache_table. Newly-saved content needs to
                # propagate to both saved and unsaved cache tables.
                if is_unsaved_module:
                    target_cache_table = self.writable_env.unsaved_contents_cache_table
                    target_cache_table.set_key_in_cache(key, self.produce_value(
                        key,
                        self.upstream_get(use_saved_contents_of_dependents=False),
                        current_env_getter=target_cache_table.look_up_key_in_cache
                    ))
                    downstream_deps |= self.writable_env.dependencies.get(key, set())
            elif is_unsaved_module:
                target_cache_table = self.writable_env.unsaved_contents_cache_table
                target_cache_table.set_key_in_cache(key, self.produce_value(
                    key,
                    self.upstream_get(use_saved_contents_of_dependents=False),
                    current_env_getter=target_cache_table.look_up_key_in_cache
                ))
                downstream_deps |= self.writable_env.dependencies.get(key, set())

        return downstream_deps

    def update(self, module: str, code: str, is_saved_content: bool) -> Set[str]:
        if is_saved_content:
            self.writable_env.unsaved_modules.discard(module)
        else:
            self.writable_env.unsaved_modules.add(module)

        if self.upstream_env is None:
            raise NotImplementedError()
        else:
            keys_to_update = self.upstream_env.update(module, code, is_saved_content)
            return self.update_for_push(keys_to_update, is_saved_content)

    def read_only(self, use_saved_contents_of_dependents: bool) -> ReadOnlyEnv:
        return lambda key, dependency: self.get(key, dependency, use_saved_contents_of_dependents=use_saved_contents_of_dependents)

    def add_unsaved_module_to_all_environments(self, module: str) -> None:
        self.writable_env.unsaved_modules.add(module)
        if self.upstream_env is not None:
            self.upstream_env.add_unsaved_module_to_all_environments(module)


# "module_name"
Module: TypeAlias = str
Code: TypeAlias = str


@dataclasses.dataclass
class WritableCodeEnv(WritableEnv[Code]):
    """A singleton code environment. This mimics how our shared-memory tables are singletons."""

    codes: CachedTable[Code] = CachedTable({})
    _writable_code_env: "Optional[WritableEnv[Code]]" = None

    @staticmethod
    def get_env(codes: Dict[Module, Code]) -> WritableEnv[Code]:
        # Steven: This is silly, but it kind of mimics why our ocaml codebase cannot easily
        # do overlays - use a global rather than a first-class value to store code.
        # This will force us to do gymnastics in the overlay!
        WritableCodeEnv.codes = CachedTable(codes)

        # Pradeep: Making this a singleton should preserve the above constraint.
        if WritableCodeEnv._writable_code_env is None:
            WritableCodeEnv._writable_code_env = WritableEnv[Code](saved_contents_cache_table=WritableCodeEnv.codes)

        # pyre-ignore[7]: Expected `None` but got `Optional[WritableEnv[str]]`.]
        return WritableCodeEnv._writable_code_env

    @staticmethod
    def clear() -> None:
        WritableCodeEnv._writable_code_env = None

@dataclasses.dataclass(init=False)
class CodeEnv(EnvTable[Code]):
    def __init__(self, writable_env: WritableEnv[Code], upstream_env: Literal[None]) -> None:
        super().__init__(writable_env, upstream_env=upstream_env)

    @staticmethod
    def produce_value(key: Module, upstream_get: Any, current_env_getter: Any) -> Code:
        return current_env_getter(key)

    def update(self, module: str, code: str, is_saved_content: bool) -> Set[str]:
        # Note 1: I was a bit sleepy when I wrote this function, so
        # double-check the logic here.

        # Note 2: We disregard the value of `is_saved_content` here because,
        # whether `module` is saved or unsaved, we want to set its contents.

        # `CodeEnv` does not have an upstream environment. So, we have to
        # override the default `update` method to set the value before we
        # "produce" it. (This is what `basic.py` does too.)
        target_cache_table = (self.writable_env.unsaved_contents_cache_table
                              if module in self.writable_env.unsaved_modules
                              else self.writable_env.saved_contents_cache_table)
        target_cache_table.set_key_in_cache(module, code)
        return cast(Set[str], self.writable_env.dependencies[module])


@dataclasses.dataclass
class AstEnv(EnvTable[ast.AST]):
    def __init__(self, writable_env: WritableEnv[ast.AST], upstream_env: CodeEnv) -> None:
        super().__init__(writable_env, upstream_env)

    @staticmethod
    def produce_value(key: Module, upstream_get: Any, current_env_getter: Any) -> ast.AST:
        code = upstream_get(key, dependency=key)
        return ast.parse(textwrap.dedent(code))


# "module_name.ClassName"
ClassName: TypeAlias = str


@dataclasses.dataclass
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


@dataclasses.dataclass
class ClassParentsEnv(EnvTable[ClassAncestors]):
    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.ClassDef], current_env_getter: Any):
        class_def = upstream_get(key, dependency=key)
        return [
            ast.unparse(b)
            for b in class_def.bases
        ]

@dataclasses.dataclass
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
    WritableCodeEnv.clear()
    code_env = CodeEnv(writable_env=WritableCodeEnv.get_env(code), upstream_env=None)
    ast_env = AstEnv(writable_env=WritableEnv[ast.AST](), upstream_env=code_env)
    class_body_env = ClassBodyEnv(writable_env=WritableEnv[ast.ClassDef](), upstream_env=ast_env)
    class_parents_env = ClassParentsEnv(writable_env=WritableEnv[ClassAncestors](), upstream_env=class_body_env)
    class_grandparents_env = ClassGrandparentsEnv(writable_env=WritableEnv[ClassAncestors](), upstream_env=class_parents_env)
    return (
        code_env,
        ast_env,
        class_body_env,
        class_parents_env,
        class_grandparents_env
    )
