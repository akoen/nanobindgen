"""Declarative schema for the @nb_* Doxygen-tag namespace.

A single TAG_SCHEMA table drives both validation (validate.py) and emission
(emit.py). To add a tag, add one row here and reference it from emit.py.
"""

from dataclasses import dataclass, field

TARGETS = frozenset({"class", "method", "free", "enum"})


@dataclass(frozen=True)
class Tag:
    target: frozenset[str]
    arity: str  # "flag" | "once" | "repeatable"
    takes_value: bool = True
    excludes: frozenset[str] = field(default_factory=frozenset)


def _t(*targets: str) -> frozenset[str]:
    return frozenset(targets)


def _e(*tags: str) -> frozenset[str]:
    return frozenset(tags)


TAG_SCHEMA: dict[str, Tag] = {
    "nb": Tag(target=_t("class", "method", "free", "enum"), arity="flag", takes_value=False),
    "nb_name": Tag(
        target=_t("class", "method", "free", "enum"),
        arity="once",
        excludes=_e("nb_prop_ro", "nb_prop_rw"),
    ),
    "nb_inherit": Tag(target=_t("class"), arity="repeatable"),
    "nb_intrusive_ptr": Tag(target=_t("class"), arity="flag", takes_value=False),
    "nb_dynamic_attr": Tag(target=_t("class"), arity="flag", takes_value=False),
    "nb_final": Tag(target=_t("class"), arity="flag", takes_value=False),
    "nb_weak_ref": Tag(target=_t("class"), arity="flag", takes_value=False),
    "nb_static": Tag(
        target=_t("method"),
        arity="flag",
        takes_value=False,
        excludes=_e("nb_init", "nb_new"),
    ),
    "nb_init": Tag(
        target=_t("method"),
        arity="flag",
        takes_value=False,
        excludes=_e("nb_static", "nb_new", "nb_prop_ro", "nb_prop_rw"),
    ),
    "nb_new": Tag(
        target=_t("method"),
        arity="flag",
        takes_value=False,
        excludes=_e("nb_static", "nb_init", "nb_prop_ro", "nb_prop_rw"),
    ),
    "nb_prop_ro": Tag(
        target=_t("method"),
        arity="once",
        excludes=_e("nb_init", "nb_new", "nb_prop_rw", "nb_name"),
    ),
    "nb_prop_rw": Tag(
        target=_t("method"),
        arity="once",
        excludes=_e("nb_init", "nb_new", "nb_prop_ro", "nb_name"),
    ),
    "nb_extra": Tag(target=_t("class", "method", "free", "enum"), arity="repeatable"),
    "nb_sig": Tag(target=_t("method", "free"), arity="once"),
    "nb_doc": Tag(target=_t("class", "method", "free", "enum"), arity="once"),
    "nb_arithmetic": Tag(target=_t("enum"), arity="flag", takes_value=False),
    "nb_flag": Tag(target=_t("enum"), arity="flag", takes_value=False),
}
