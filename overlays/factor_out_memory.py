import ast
import dataclasses
from typing import (
    Any, Dict, Generic, Protocol, Set, Tuple, TypeVar, List, Optional, cast
)

from typing_extensions import TypeAlias
import textwrap


T = TypeVar("T")



class ReadOnlyEnv(Generic[T], Protocol):
    def __call__(self, key: str, dependency: str) -> T:
        ...


class WritableEnv(Generic[T]):
    # It's a pain to type this well so I'll place fast and loose
    # with the types here to avoid an explosion of generics
    cached: Dict[str, T]  # object is the value type
    dependencies: Dict[str, Set[object]]  # object is the
    upstream_env: Optional["EnvTable"]

    def __init__(self, cached: Optional[Dict[str, T]] = None) -> None:
        self.cached = cached if cached is not None else {}
        self.dependencies = {}
        self.upstream_env = None


class EnvTable(Generic[T]):
    writable_env: WritableEnv[T]

    def __init__(self, writable_env) -> None:
        self.writable_env = writable_env

    @property
    def upstream_get(self) -> ReadOnlyEnv:
        if self.writable_env.upstream_env is None:
            return ...  # typing this correctly is annoying and not illuminating
        else:
            return self.writable_env.upstream_env.read_only()

    @staticmethod
    def produce_value(key: str, upstream_get: Any) -> T:
        "Must be implemented by child environments"
        raise NotImplementedError()

    def register_dependency(self, key: str, dependency: str) -> None:
        self.writable_env.dependencies[key] = self.writable_env.dependencies.get(key, set())
        self.writable_env.dependencies[key].add(dependency)

    def get(self, key: str, dependency: str) -> T:
        self.register_dependency(key, dependency)
        if key not in self.writable_env.cached:
            self.writable_env.cached[key] = self.produce_value(
                key,
                self.upstream_get,
            )
        return self.writable_env.cached[key]

    def update_for_push(self, keys_to_update: Set[str]) -> Set[str]:
        downstream_deps = set()
        for key in keys_to_update:
            self.writable_env.cached[key] = self.produce_value(key, self.upstream_get)
            downstream_deps |= self.writable_env.dependencies.get(key, set())
        return downstream_deps

    def update(self, module: str, code: str) -> Set[str]:
        if self.writable_env.upstream_env is None:
            raise NotImplementedError()
        else:
            keys_to_update = self.writable_env.upstream_env.update(module, code)
            return self.update_for_push(keys_to_update)

    def read_only(self) -> ReadOnlyEnv:
        return self.get


# "module_name"
Module: TypeAlias = str
Code: TypeAlias = str


class WritableCodeEnv(WritableEnv[Code]):
    """A singleton code environment. This mimics how our shared-memory tables are singletons."""

    codes: Dict[Module, Code] = {}
    _writable_code_env: "Optional[WritableEnv[Code]]" = None

    @staticmethod
    def get_env(codes: Dict[Module, Code]) -> None:
        # Steven: This is silly, but it kind of mimics why our ocaml codebase cannot easily
        # do overlays - use a global rather than a first-class value to store code.
        # This will force us to do gymnastics in the overlay!
        WritableCodeEnv.codes = codes

        # Pradeep: Making this a singleton should preserve the above constraint.
        if WritableCodeEnv._writable_code_env is None:
            WritableCodeEnv._writable_code_env = WritableEnv[Code](cached=WritableCodeEnv.codes)

        # pyre-ignore[7]: Expected `None` but got `Optional[WritableEnv[str]]`.]
        return WritableCodeEnv._writable_code_env

class CodeEnv(EnvTable[Code]):

    def __init__(self, codes: Dict[Module, Code]) -> None:
        super().__init__(WritableCodeEnv.get_env(codes))

    @staticmethod
    def produce_value(key: Module, upstream_get: Any) -> Code:
        return WritableCodeEnv.codes[key]

    def update(self, module: str, code: str) -> Set[str]:
        # `CodeEnv` does not have an upstream environment. So, we have to
        # override the default `update` method to set the value before we
        # "produce" it. (This is what `basic.py` does too.)
        self.writable_env.cached[module] = code
        return cast(Set[str], self.writable_env.dependencies[module])


class AstEnv(EnvTable[ast.AST]):
    def __init__(self, upstream_env: CodeEnv):
        super().__init__(WritableEnv[ast.AST]())
        self.writable_env.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: Module, upstream_get: Any) -> ast.AST:
        code = upstream_get(key, dependency=key)
        return ast.parse(textwrap.dedent(code))


# "module_name.ClassName"
ClassName: TypeAlias = str


class ClassBodyEnv(EnvTable[ast.ClassDef]):

    def __init__(self, upstream_env: AstEnv):
        super().__init__(WritableEnv[ast.ClassDef]())
        self.writable_env.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.AST]):
        module, relative_name = key.split(".")
        ast_ = upstream_get(key=module, dependency=key)
        # pyre-fixme[16]: `_ast.AST` has no attribute `body`.
        for class_def in ast_.body:
            if class_def.name == relative_name:
                return class_def


ClassAncestors: TypeAlias = List[str]


class ClassParentsEnv(EnvTable[ClassAncestors]):

    def __init__(self, upstream_env: ClassBodyEnv):
        super().__init__(WritableEnv[ClassAncestors]())
        self.writable_env.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.ClassDef]):
        class_def = upstream_get(key, dependency=key)
        return [
            ast.unparse(b)
            for b in class_def.bases
        ]

class ClassGrandparentsEnv(EnvTable[ClassAncestors]):

    def __init__(self, upstream_env: ClassParentsEnv):
        super().__init__(WritableEnv[ClassAncestors]())
        self.writable_env.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ClassAncestors]):
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
    code_env = CodeEnv(code)
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
