"""Immutable IR records produced by parse.py and consumed by validate.py / emit.py.

Source locations are 1-based (line, col); producers convert from tree-sitter's
0-based start_point. TagSet defensively wraps its mapping containers in
MappingProxyType so the IR is genuinely immutable end-to-end.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class SourceLoc:
    path: str
    line: int  # 1-based
    col: int   # 1-based


@dataclass(frozen=True, slots=True)
class Param:
    type: str
    name: str
    default: str | None  # raw C++ default expression, or None


@dataclass(frozen=True, slots=True)
class DocIR:
    brief: str = ""
    detail: str = ""
    params: tuple[tuple[str, str], ...] = ()  # (name, description)
    returns: str = ""
    raises: tuple[tuple[str, str], ...] = ()  # (exception_type, description)
    override: str | None = None  # @nb_doc body, if present


@dataclass(frozen=True, slots=True)
class TagSet:
    flags: frozenset[str] = frozenset()
    values: Mapping[str, str] = field(default_factory=dict)              # once-arity tag -> body
    repeats: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # repeatable tag -> bodies in source order
    locations: Mapping[str, tuple[SourceLoc, ...]] = field(default_factory=dict)  # tag_name -> all occurrences in source order

    def __post_init__(self) -> None:
        # Defensively wrap mapping inputs as read-only views so callers cannot
        # mutate the IR after construction.
        for attr in ("values", "repeats", "locations"):
            current = getattr(self, attr)
            if not isinstance(current, MappingProxyType):
                object.__setattr__(self, attr, MappingProxyType(dict(current)))

    def has(self, name: str) -> bool:
        return name in self.flags or name in self.values or name in self.repeats

    def get(self, name: str) -> str | None:
        """Body of a once-arity tag, or None if absent / a flag / repeatable."""
        return self.values.get(name)

    def get_all(self, name: str) -> tuple[str, ...]:
        """All bodies of a repeatable tag, in source order, or () if absent."""
        return self.repeats.get(name, ())

    def first_loc(self, name: str) -> SourceLoc | None:
        """First source location of a tag, or None if absent."""
        locs = self.locations.get(name, ())
        return locs[0] if locs else None


@dataclass(frozen=True, slots=True)
class MethodIR:
    cpp_name: str
    loc: SourceLoc
    params: tuple[Param, ...]
    is_cpp_static: bool
    tags: TagSet
    doc: DocIR


@dataclass(frozen=True, slots=True)
class FreeFunctionIR:
    cpp_name: str
    loc: SourceLoc
    params: tuple[Param, ...]
    tags: TagSet
    doc: DocIR


@dataclass(frozen=True, slots=True)
class ClassIR:
    cpp_name: str
    loc: SourceLoc
    tags: TagSet
    doc: DocIR
    methods: tuple[MethodIR, ...]


@dataclass(frozen=True, slots=True)
class EnumValueIR:
    cpp_name: str
    value: str | None  # raw C++ value expression, or None
    doc: DocIR
    loc: SourceLoc


@dataclass(frozen=True, slots=True)
class EnumIR:
    cpp_name: str
    loc: SourceLoc
    tags: TagSet
    doc: DocIR
    values: tuple[EnumValueIR, ...]


@dataclass(frozen=True, slots=True)
class HeaderIR:
    path: str
    classes: tuple[ClassIR, ...]
    free_functions: tuple[FreeFunctionIR, ...]
    enums: tuple[EnumIR, ...]
