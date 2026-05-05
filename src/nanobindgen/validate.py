"""IR -> diagnostics. Applies tags.py schema rules. Errors collected, not raised."""

import difflib

from .errors import ErrorCollector
from .ir import ClassIR, HeaderIR, MethodIR, SourceLoc, TagSet
from .tags import TAG_SCHEMA

_SUGGESTION_CUTOFF = 0.6


def validate(header: HeaderIR, collector: ErrorCollector) -> None:
    for cls in header.classes:
        _validate_entity(cls.tags, "class", collector)
        _validate_doc_overrides(cls, collector)
        _validate_extra_duplication(cls, collector)
        for method in cls.methods:
            _validate_entity(method.tags, "method", collector)
            _validate_param_docs(method, collector)
            _validate_doc_overrides(method, collector)
        _validate_property_pairing(cls, collector)
        _validate_overload_consistency(cls, collector)
    for fn in header.free_functions:
        _validate_entity(fn.tags, "free", collector)
        _validate_param_docs(fn, collector)
        _validate_doc_overrides(fn, collector)
    for enum in header.enums:
        _validate_entity(enum.tags, "enum", collector)
        _validate_doc_overrides(enum, collector)
        _validate_extra_duplication(enum, collector)


def _all_tag_names(tags: TagSet) -> set[str]:
    return set(tags.flags) | set(tags.values) | set(tags.repeats)


def _loc(tags: TagSet, name: str) -> SourceLoc:
    return tags.first_loc(name) or SourceLoc("<unknown>", 0, 0)


def _validate_entity(
    tags: TagSet,
    kind: str,
    collector: ErrorCollector,
) -> None:
    names = _all_tag_names(tags)
    nb_tag_names = {n for n in names if n == "nb" or n.startswith("nb_")}

    if not nb_tag_names:
        return  # No @nb_* tags at all -> nothing to validate.

    has_marker = "nb" in tags.flags

    # Sorted for deterministic diagnostic order — important for golden tests.
    for name in sorted(nb_tag_names):
        loc = _loc(tags, name)

        # Rule 1: unknown tag.
        if name not in TAG_SCHEMA:
            suggestion = ""
            # Score all known tags; break ties alphabetically so the result is stable.
            scores = [
                (difflib.SequenceMatcher(None, name, key).ratio(), key)
                for key in TAG_SCHEMA
            ]
            scores.sort(key=lambda x: (-x[0], x[1]))
            if scores and scores[0][0] >= _SUGGESTION_CUTOFF:
                suggestion = f" — did you mean @{scores[0][1]}?"
            collector.error(
                loc.path, loc.line, loc.col,
                f"unknown tag @{name}{suggestion}",
            )
            continue

        schema = TAG_SCHEMA[name]

        # Rule 2: wrong target.
        if kind not in schema.target:
            valid = ", ".join(sorted(schema.target))
            collector.error(
                loc.path, loc.line, loc.col,
                f"@{name} is not valid on {kind} (valid on {valid})",
            )

        # Rule 3 + 5: arity violation / required body.
        in_flags = name in tags.flags
        in_values = name in tags.values
        in_repeats = name in tags.repeats

        if schema.arity == "flag":
            if in_values or in_repeats:
                collector.error(
                    loc.path, loc.line, loc.col,
                    f"@{name} does not take a value",
                )
        elif schema.arity == "once":
            if in_flags:
                collector.error(
                    loc.path, loc.line, loc.col,
                    f"@{name} requires a value",
                )
            if in_repeats:
                collector.error(
                    loc.path, loc.line, loc.col,
                    f"@{name} can only appear once",
                )
        elif schema.arity == "repeatable":
            if in_flags:
                collector.error(
                    loc.path, loc.line, loc.col,
                    f"@{name} requires a value",
                )

        # Rule 4: mutual exclusion. Emit only when name < excluded so each pair
        # produces a single diagnostic instead of two symmetric ones.
        for excluded in schema.excludes:
            if name < excluded and excluded in names:
                collector.error(
                    loc.path, loc.line, loc.col,
                    f"@{name} and @{excluded} cannot both be set",
                )

    # Rule 7: any @nb_* tag without bare @nb.
    if not has_marker:
        for name in sorted(nb_tag_names):
            if name == "nb":
                continue
            loc = _loc(tags, name)
            collector.error(
                loc.path, loc.line, loc.col,
                f"@{name} found but @nb is missing — did you forget to mark this for binding?",
            )
            break  # one error per entity is enough


def _python_name_of(method: MethodIR) -> str:
    """Resolve the Python-side name a method binds to."""
    if "nb_prop_ro" in method.tags.values:
        return method.tags.values["nb_prop_ro"]
    if "nb_prop_rw" in method.tags.values:
        return method.tags.values["nb_prop_rw"]
    if "nb_name" in method.tags.values:
        return method.tags.values["nb_name"]
    return method.cpp_name


def _kind_of(method: MethodIR, class_name: str) -> str:
    if "nb_init" in method.tags.flags or method.cpp_name == class_name:
        return "init"
    if "nb_new" in method.tags.flags:
        return "new_"
    if "nb_prop_ro" in method.tags.values:
        return "prop_ro"
    if "nb_prop_rw" in method.tags.values:
        return "prop_rw"
    if "nb_static" in method.tags.flags or method.is_cpp_static:
        return "static"
    return "method"


def _validate_property_pairing(cls: ClassIR, collector: ErrorCollector) -> None:
    rw_roles: dict[str, list[MethodIR]] = {}  # name -> methods tagged @nb_prop_rw
    for m in cls.methods:
        if "nb_prop_rw" in m.tags.values:
            rw_roles.setdefault(m.tags.values["nb_prop_rw"], []).append(m)

    for name, methods in rw_roles.items():
        if len(methods) == 1:
            m = methods[0]
            loc = m.loc
            # Heuristic: if method has 0 params -> it's a getter, missing setter.
            #            if method has >=1 param -> it's a setter, missing getter.
            role = "getter" if len(m.params) == 0 else "setter"
            other = "setter" if role == "getter" else "getter"
            collector.error(
                loc.path, loc.line, loc.col,
                f'@nb_prop_rw "{name}" has a {role} but no {other}',
            )
        elif len(methods) > 2:
            for m in methods[2:]:
                collector.error(
                    m.loc.path, m.loc.line, m.loc.col,
                    f'@nb_prop_rw "{name}" has more than two methods',
                )


def _validate_overload_consistency(cls: ClassIR, collector: ErrorCollector) -> None:
    by_pyname: dict[str, list[MethodIR]] = {}
    for m in cls.methods:
        if "nb_prop_ro" in m.tags.values or "nb_prop_rw" in m.tags.values:
            continue  # properties don't participate in overload sets
        py = _python_name_of(m)
        by_pyname.setdefault(py, []).append(m)

    for py, methods in by_pyname.items():
        if len(methods) < 2:
            continue
        kinds = {_kind_of(m, cls.cpp_name) for m in methods}
        if len(kinds) > 1:
            for m in methods:
                collector.error(
                    m.loc.path, m.loc.line, m.loc.col,
                    f"overload {py!r}: participants must share the same kind "
                    f"(got {sorted(kinds)})",
                )


def _validate_param_docs(method_or_fn, collector: ErrorCollector) -> None:
    cpp_names = {p.name for p in method_or_fn.params if p.name}
    doc_names = {n for n, _ in method_or_fn.doc.params}
    loc = method_or_fn.loc

    for name in sorted(doc_names - cpp_names):
        collector.warning(
            loc.path, loc.line, loc.col,
            f"@param '{name}' does not match any parameter in {method_or_fn.cpp_name!r}",
        )
    for name in sorted(cpp_names - doc_names):
        collector.warning(
            loc.path, loc.line, loc.col,
            f"parameter '{name}' has no @param documentation in {method_or_fn.cpp_name!r}",
        )


def _validate_doc_overrides(method_or_fn_or_class, collector: ErrorCollector) -> None:
    doc = getattr(method_or_fn_or_class, "doc", None)
    if doc is None:
        return
    if doc.override is not None and doc.brief:
        loc = method_or_fn_or_class.loc
        collector.warning(
            loc.path, loc.line, loc.col,
            "@nb_doc is set; @brief is ignored",
        )


_DEDICATED_TAG_HINTS = {
    "nb_intrusive_ptr": "nb::intrusive_ptr",
    "nb_dynamic_attr": "nb::dynamic_attr",
    "nb_final": "nb::is_final",
    "nb_weak_ref": "nb::is_weak_referenceable",
    "nb_arithmetic": "nb::is_arithmetic",
    "nb_flag": "nb::is_flag",
}


def _validate_extra_duplication(cls_or_enum, collector: ErrorCollector) -> None:
    extras = cls_or_enum.tags.repeats.get("nb_extra", ())
    flags = cls_or_enum.tags.flags
    loc = cls_or_enum.loc
    for tag_name, hint in _DEDICATED_TAG_HINTS.items():
        if tag_name in flags and any(hint in e for e in extras):
            collector.warning(
                loc.path, loc.line, loc.col,
                f"@nb_extra contains {hint!r} which duplicates @{tag_name}",
            )
