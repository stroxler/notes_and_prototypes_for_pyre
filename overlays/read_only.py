import ast
import dataclasses
from typing import (
    Any, Dict, Generic, Protocol, Set, Tuple, TypeVar, List, Optional
)

from typing_extensions import TypeAlias
import textwrap


T = TypeVar("T")



class ReadOnlyEnv(Generic[T], Protocol):
    def __call__(key: str, dependency: str) -> T:
        ...


class EnvTable(Generic[T]):
    # It's a pain to type this well so I'll place fast and loose
    # with the types here to avoid an explosion of generics

    cached: Dict[str, T]  # object is the value type
    dependencies: Dict[str, Set[object]]  # object is the
    upstream_env: Optional["EnvTable"]

    def __init__(self):
        self.cached = {}
        self.dependencies = {}
        self.upstream_env = None

    @property
    def upstream_get(self) -> ReadOnlyEnv:
        if self.upstream_env is None:
            return ...  # typing this correctly is annoying and not illuminating
        else:
            return self.upstream_env.read_only()

    @staticmethod
    def produce_value(key: str, upstream_get: Any) -> T:
        "Must be implemented by child environments"
        raise NotImplementedError()

    def register_dependency(self, key: str, dependency: str) -> None:
        self.dependencies[key] = self.dependencies.get(key, set())
        self.dependencies[key].add(dependency)

    def get(self, key: str, dependency: str) -> T:
        self.register_dependency(key, dependency)
        if key not in self.cached:
            self.cached[key] = self.produce_value(
                key,
                self.upstream_get,
            )
        return self.cached[key]

    def update_for_push(self, keys_to_update: Set[str]) -> Set[str]:
        downstream_deps = set()
        for key in keys_to_update:
            self.cached[key] = self.produce_value(key, self.upstream_get)
            downstream_deps |= self.dependencies.get(key, set())
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


class CodeEnv(EnvTable[Code]):
    codes: Dict[Module, Code] = {}

    def __init__(self, codes: Dict[Module, Code]) -> None:
        super().__init__()
        # This is silly, but it kind of mimics why our ocaml codebase cannot easily
        # do overlays - use a global rather than a first-class value to store code.
        # This will force us to do gymnastics in the overlay!
        CodeEnv.codes = codes

    @staticmethod
    def produce_value(key: Module, upstream_get: Any) -> str:
        return CodeEnv.codes[key]

    def update(self, module: str, code: str) -> Set[str]:
        CodeEnv.codes[module] = code
        self.cached[module] = self.produce_value(module, upstream_get=None)
        return self.dependencies[module]


class AstEnv(EnvTable[ast.AST]):
    def __init__(self, upstream_env: CodeEnv):
        super().__init__()
        self.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: Module, upstream_get: ReadOnlyEnv[Code]):
        code = upstream_get(key, dependency=key)
        return ast.parse(textwrap.dedent(code))


# "module_name.ClassName"
ClassName: TypeAlias = str


class ClassBodyEnv(EnvTable[ast.ClassDef]):

    def __init__(self, upstream_env: AstEnv):
        super().__init__()
        self.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.AST]):
        module, relative_name = key.split(".")
        ast_ = upstream_get(key=module, dependency=key)
        for class_def in ast_.body:
            if class_def.name == relative_name:
                return class_def


ClassAncestors: TypeAlias = List[str]


class ClassParentsEnv(EnvTable[ClassAncestors]):

    def __init__(self, upstream_env: ClassBodyEnv):
        super().__init__()
        self.upstream_env = upstream_env

    @staticmethod
    def produce_value(key: ClassName, upstream_get: ReadOnlyEnv[ast.ClassDef]):
        class_def = upstream_get(key, dependency=key)
        return [
            ast.unparse(b)
            for b in class_def.bases
        ]

class ClassGrandparentsEnv(EnvTable[ClassAncestors]):

    def __init__(self, upstream_env: ClassParentsEnv):
        super().__init__()
        self.upstream_env = upstream_env

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
