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
    """1-based source location for diagnostics."""

    path: str
    line: int  # 1-based
    col: int  # 1-based


@dataclass(frozen=True, slots=True)
class Param:
    """A function or method parameter."""

    type: str
    name: str
    default: str | None  # raw C++ default expression, or None


@dataclass(frozen=True, slots=True)
class DocIR:
    """Doxygen-derived docstring components for one entity."""

    brief: str = ""
    detail: str = ""
    params: tuple[tuple[str, str], ...] = ()  # (name, description)
    returns: str = ""
    raises: tuple[tuple[str, str], ...] = ()  # (exception_type, description)
    override: str | None = None  # @nb_doc body, if present


@dataclass(frozen=True, slots=True)
class TagSet:
    """Parsed @nb_* tags for one entity, classified by arity with source locations."""

    flags: frozenset[str] = frozenset()
    values: Mapping[str, str] = field(default_factory=dict)  # once-arity tag -> body
    repeats: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )  # repeatable tag -> bodies in source order
    locations: Mapping[str, tuple[SourceLoc, ...]] = field(
        default_factory=dict
    )  # tag_name -> all occurrences in source order

    def __post_init__(self) -> None:
        """Wrap mapping inputs as read-only views so the IR is genuinely immutable."""
        for attr in ("values", "repeats", "locations"):
            current = getattr(self, attr)
            if not isinstance(current, MappingProxyType):
                object.__setattr__(self, attr, MappingProxyType(dict(current)))

    def has(self, name: str) -> bool:
        """True if `name` appears as a flag, once-value, or repeatable."""
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
    """A class member function (instance, static, constructor, or factory)."""

    cpp_name: str
    loc: SourceLoc
    params: tuple[Param, ...]
    is_cpp_static: bool
    tags: TagSet
    doc: DocIR


@dataclass(frozen=True, slots=True)
class FreeFunctionIR:
    """A non-member function declared at file scope."""

    cpp_name: str
    loc: SourceLoc
    params: tuple[Param, ...]
    tags: TagSet
    doc: DocIR


@dataclass(frozen=True, slots=True)
class ClassIR:
    """A C++ class with its methods and binding tags."""

    cpp_name: str
    loc: SourceLoc
    tags: TagSet
    doc: DocIR
    methods: tuple[MethodIR, ...]


@dataclass(frozen=True, slots=True)
class EnumValueIR:
    """A single enumerator within an enum."""

    cpp_name: str
    value: str | None  # raw C++ value expression, or None
    doc: DocIR
    loc: SourceLoc


@dataclass(frozen=True, slots=True)
class EnumIR:
    """A C++ enum (typically `enum class`)."""

    cpp_name: str
    loc: SourceLoc
    tags: TagSet
    doc: DocIR
    values: tuple[EnumValueIR, ...]


@dataclass(frozen=True, slots=True)
class HeaderIR:
    """Top-level IR for one parsed header file."""

    path: str
    classes: tuple[ClassIR, ...]
    free_functions: tuple[FreeFunctionIR, ...]
    enums: tuple[EnumIR, ...]
