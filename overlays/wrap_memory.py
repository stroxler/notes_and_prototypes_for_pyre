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


class CachedTable(Protocol[T]):
    def has_key_in_cache(self, key: str) -> bool: ...

    def set_key_in_cache(self, key: str, value: T) -> None: ...

    def look_up_key_in_cache(self, key: str) -> T: ...

@dataclasses.dataclass
class DictionaryCachedTable(Generic[T]):
    _cached: Dict[str, T]

    def has_key_in_cache(self, key: str) -> bool:
        return key in self._cached

    def set_key_in_cache(self, key: str, value: T) -> None:
        self._cached[key] = value

    def look_up_key_in_cache(self, key: str) -> T:
        return self._cached[key]

@dataclasses.dataclass
class WrappedCacheTable(Generic[T]):
    original_cache_table: CachedTable[T]
    overridden_module: str
    overridden_cache_table: CachedTable[T]

    def cache_table(self, key: str) -> CachedTable[T]:
        # Note: For some environments, the key is the class name. So, use
        # `startswith` for the sake of the toy project.
        return self.overridden_cache_table if key.startswith(self.overridden_module) else self.original_cache_table

    def has_key_in_cache(self, key: str) -> bool:
        return self.cache_table(key).has_key_in_cache(key)

    def set_key_in_cache(self, key: str, value: T) -> None:
        self.cache_table(key).set_key_in_cache(key, value)

    def look_up_key_in_cache(self, key: str) -> T:
        """This replaces the exception-raising lookup: `d[key]`."""
        return self.cache_table(key).look_up_key_in_cache(key)

@dataclasses.dataclass
class WritableEnv(Generic[T]):
    # It's a pain to type this well so I'll place fast and loose
    # with the types here to avoid an explosion of generics
    cached_table: CachedTable[T] = dataclasses.field(default_factory=lambda: DictionaryCachedTable({}))
    dependencies: Dict[str, Set[object]] = dataclasses.field(default_factory=dict)



@dataclasses.dataclass
class EnvTable(Generic[T]):
    writable_env: WritableEnv[T]
    upstream_env: Optional["EnvTable"] = None

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

    def register_dependency(self, key: str, dependency: str) -> None:
        self.writable_env.dependencies[key] = self.writable_env.dependencies.get(key, set())
        self.writable_env.dependencies[key].add(dependency)

    def get(self, key: str, dependency: str) -> T:
        self.register_dependency(key, dependency)
        if not self.writable_env.cached_table.has_key_in_cache(key):
            self.writable_env.cached_table.set_key_in_cache(key, self.produce_value(
                key,
                self.upstream_get,
                current_env_getter=self.writable_env.cached_table.look_up_key_in_cache
            ))
        return self.writable_env.cached_table.look_up_key_in_cache(key)

    def update_for_push(self, keys_to_update: Set[str]) -> Set[str]:
        downstream_deps = set()
        for key in keys_to_update:
            self.writable_env.cached_table.set_key_in_cache(key, self.produce_value(
                key,
                self.upstream_get,
                current_env_getter=self.writable_env.cached_table.look_up_key_in_cache
            ))
            downstream_deps |= self.writable_env.dependencies.get(key, set())
        return downstream_deps

    def update(self, module: str, code: str) -> Set[str]:
        if self.upstream_env is None:
            raise NotImplementedError()
        else:
            keys_to_update = self.upstream_env.update(module, code)
            return self.update_for_push(keys_to_update)

    def read_only(self) -> ReadOnlyEnv:
        return self.get


# "module_name"
Module: TypeAlias = str
Code: TypeAlias = str


@dataclasses.dataclass
class WritableCodeEnv(WritableEnv[Code]):
    """A singleton code environment. This mimics how our shared-memory tables are singletons."""

    codes: CachedTable[Code] = DictionaryCachedTable({})
    _writable_code_env: "Optional[WritableEnv[Code]]" = None

    @staticmethod
    def get_env(codes: Dict[Module, Code]) -> WritableEnv[Code]:
        # Steven: This is silly, but it kind of mimics why our ocaml codebase cannot easily
        # do overlays - use a global rather than a first-class value to store code.
        # This will force us to do gymnastics in the overlay!
        WritableCodeEnv.codes = DictionaryCachedTable(codes)

        # Pradeep: Making this a singleton should preserve the above constraint.
        if WritableCodeEnv._writable_code_env is None:
            WritableCodeEnv._writable_code_env = WritableEnv[Code](cached_table=WritableCodeEnv.codes)

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

    def update(self, module: str, code: str) -> Set[str]:
        # `CodeEnv` does not have an upstream environment. So, we have to
        # override the default `update` method to set the value before we
        # "produce" it. (This is what `basic.py` does too.)
        self.writable_env.cached_table.set_key_in_cache(module, code)
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
