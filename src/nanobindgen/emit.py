"""IR -> C++ string. Pure functions; no I/O."""

from collections import defaultdict

from .ir import ClassIR, DocIR, EnumIR, FreeFunctionIR, HeaderIR, MethodIR, Param

TAB = "    "

_DELIMITERS = ("nbdoc", "nbdoc_x", "nbdoc_xx", "nbdoc_xxx")


def raw_string(s: str) -> str:
    """Wrap s as a C++ raw string literal, picking a delimiter that doesn't collide."""
    for d in _DELIMITERS:
        marker = f'){d}"'
        if marker not in s:
            return f'R"{d}({s}){d}"'
    raise ValueError("No safe delimiter found for raw string content")


def gen_docstring(doc: DocIR) -> str:
    """Render a DocIR into a Google-style docstring (override short-circuits)."""
    if doc.override is not None:
        return doc.override

    sections: list[str] = []
    if doc.brief:
        sections.append(doc.brief)
    if doc.detail:
        sections.append(doc.detail)
    if doc.params:
        body = "\n".join(f"{TAB}{name}: {desc}" for name, desc in doc.params)
        sections.append(f"Args:\n{body}")
    if doc.returns:
        sections.append(f"Returns:\n{TAB}{doc.returns}")
    if doc.raises:
        body = "\n".join(f"{TAB}{exc}: {desc}" for exc, desc in doc.raises)
        sections.append(f"Raises:\n{body}")
    return "\n\n".join(sections)


_INTRUSIVE_PTR_TEMPLATE = (
    "nb::intrusive_ptr<{T}>"
    "([]({T}* o, PyObject* po) noexcept {{ o->set_self_py(po); }})"
)

_CLASS_POLICY_FLAGS = (
    ("nb_dynamic_attr", "nb::dynamic_attr()"),
    ("nb_final", "nb::is_final()"),
    ("nb_weak_ref", "nb::is_weak_referenceable()"),
)


def emit_class_head(cls: ClassIR) -> str:
    """Render the `nb::class_<T, Bases...>(m, "Py", ...)` head for one class."""
    py_name = cls.tags.get("nb_name") or cls.cpp_name
    bases = cls.tags.get_all("nb_inherit")
    template_args = ", ".join((cls.cpp_name, *bases))

    args: list[str] = ["m", f'"{py_name}"']

    docstring = gen_docstring(cls.doc)
    if docstring:
        args.append(raw_string(docstring))

    if "nb_intrusive_ptr" in cls.tags.flags:
        args.append(_INTRUSIVE_PTR_TEMPLATE.format(T=cls.cpp_name))

    for flag, snippet in _CLASS_POLICY_FLAGS:
        if flag in cls.tags.flags:
            args.append(snippet)

    args.extend(cls.tags.get_all("nb_extra"))

    return f"nb::class_<{template_args}>({', '.join(args)})"


def _python_name(method: MethodIR) -> str:
    if "nb_prop_ro" in method.tags.values:
        return method.tags.values["nb_prop_ro"]
    if "nb_prop_rw" in method.tags.values:
        return method.tags.values["nb_prop_rw"]
    return method.tags.values.get("nb_name", method.cpp_name)


def _format_param_args(params: tuple[Param, ...]) -> list[str]:
    out: list[str] = []
    for p in params:
        if p.default is not None:
            out.append(f'"{p.name}"_a = {p.default}')
        else:
            out.append(f'"{p.name}"_a')
    return out


def _is_init(method: MethodIR, class_name: str | None) -> bool:
    if "nb_init" in method.tags.flags:
        return True
    return class_name is not None and method.cpp_name == class_name


def _trailing_extras(method: MethodIR) -> list[str]:
    out: list[str] = []
    docstring = gen_docstring(method.doc)
    if docstring:
        out.append(raw_string(docstring))
    if "nb_sig" in method.tags.values:
        out.append(f'nb::sig("{method.tags.values["nb_sig"]}")')
    out.extend(method.tags.get_all("nb_extra"))
    return out


def emit_method(method: MethodIR, class_name: str) -> str:
    """Emit a chained .def... call for a class method."""
    is_static = "nb_static" in method.tags.flags or method.is_cpp_static
    init = _is_init(method, class_name)
    is_new = "nb_new" in method.tags.flags
    is_prop_ro = "nb_prop_ro" in method.tags.values
    is_prop_rw = "nb_prop_rw" in method.tags.values

    if is_prop_ro or is_prop_rw:
        # Properties go through emit_property (Task 15) at the class-emit layer.
        raise NotImplementedError(
            "emit_method does not handle properties; see emit_property"
        )

    py_name = _python_name(method)
    arg_specs = _format_param_args(method.params)
    extras = _trailing_extras(method)

    if init:
        template_params = ", ".join(p.type for p in method.params)
        return f".def(nb::init<{template_params}>(){_join_args(arg_specs, extras)})"

    if is_new:
        ref = f"&{class_name}::{method.cpp_name}"
        return f".def(nb::new_({ref}){_join_args(arg_specs, extras)})"

    def_fn = "def_static" if is_static else "def"
    ref = f"&{class_name}::{method.cpp_name}"
    return f'.{def_fn}("{py_name}", {ref}{_join_args(arg_specs, extras)})'


def _join_args(arg_specs: list[str], extras: list[str]) -> str:
    pieces = arg_specs + extras
    if not pieces:
        return ""
    return ", " + ", ".join(pieces)


def emit_property(methods: list[MethodIR], class_name: str) -> str:
    """Emit a single .def_prop_ro/rw[_static] call from one or two methods."""
    is_rw = any("nb_prop_rw" in m.tags.values for m in methods)
    is_static = all("nb_static" in m.tags.flags or m.is_cpp_static for m in methods)
    py_name = methods[0].tags.get("nb_prop_ro") or methods[0].tags.get("nb_prop_rw")

    suffix = "_static" if is_static else ""
    if is_rw:
        # Order: getter (no params) then setter.
        getter = next(m for m in methods if len(m.params) == 0)
        setter = next(m for m in methods if len(m.params) > 0)
        ref = f"&{class_name}::{getter.cpp_name}, &{class_name}::{setter.cpp_name}"
        doc_source = getter.doc
        kind = "def_prop_rw"
    else:
        getter = methods[0]
        ref = f"&{class_name}::{getter.cpp_name}"
        doc_source = getter.doc
        kind = "def_prop_ro"

    extras: list[str] = []
    docstring = gen_docstring(doc_source)
    if docstring:
        extras.append(raw_string(docstring))
    extras.extend(getter.tags.get_all("nb_extra"))
    return f'.{kind}{suffix}("{py_name}", {ref}{_join_args([], extras)})'


def emit_overload(methods: list[MethodIR], class_name: str) -> list[str]:
    """Emit one .def(...) per overload participant, using nb::overload_cast."""
    out: list[str] = []
    for m in methods:
        py_name = _python_name(m)
        template_params = ", ".join(p.type for p in m.params)
        ref = f"nb::overload_cast<{template_params}>(&{class_name}::{m.cpp_name})"
        is_static = "nb_static" in m.tags.flags or m.is_cpp_static
        def_fn = "def_static" if is_static else "def"
        arg_specs = _format_param_args(m.params)
        extras = _trailing_extras(m)
        out.append(f'.{def_fn}("{py_name}", {ref}{_join_args(arg_specs, extras)})')
    return out


def emit_free_function(fn: FreeFunctionIR) -> str:
    """Render an `m.def("py", &cpp, ...);` line for a free function."""
    py_name = fn.tags.values.get("nb_name", fn.cpp_name)
    arg_specs = _format_param_args(fn.params)

    extras: list[str] = []
    docstring = gen_docstring(fn.doc)
    if docstring:
        extras.append(raw_string(docstring))
    if "nb_sig" in fn.tags.values:
        extras.append(f'nb::sig("{fn.tags.values["nb_sig"]}")')
    extras.extend(fn.tags.get_all("nb_extra"))

    return f'm.def("{py_name}", &{fn.cpp_name}{_join_args(arg_specs, extras)});'


_ENUM_POLICY_FLAGS = (
    ("nb_arithmetic", "nb::is_arithmetic()"),
    ("nb_flag", "nb::is_flag()"),
)


def emit_enum(enum: EnumIR) -> str:
    """Render the full `nb::enum_<E>(m, "Py", ...).value(...)` block for an enum."""
    py_name = enum.tags.values.get("nb_name", enum.cpp_name)
    head_args: list[str] = ["m", f'"{py_name}"']

    docstring = gen_docstring(enum.doc)
    if docstring:
        head_args.append(raw_string(docstring))
    for flag, snippet in _ENUM_POLICY_FLAGS:
        if flag in enum.tags.flags:
            head_args.append(snippet)
    head_args.extend(enum.tags.get_all("nb_extra"))

    head = f"nb::enum_<{enum.cpp_name}>({', '.join(head_args)})"
    value_lines: list[str] = []
    for v in enum.values:
        v_args = [f'"{v.cpp_name}"', f"{enum.cpp_name}::{v.cpp_name}"]
        v_doc = gen_docstring(v.doc)
        if v_doc:
            v_args.append(raw_string(v_doc))
        value_lines.append(f"{TAB}{TAB}.value({', '.join(v_args)})")

    return f"{TAB}{head}\n" + "\n".join(value_lines) + ";"


def _group_methods(cls: ClassIR) -> list[list[MethodIR]]:
    """Group cls.methods into bind units in source order.

    - One group per property pair (or singleton).
    - One group per overload set (≥2 methods sharing Python name and not props).
    - Otherwise one group per method.

    Group iteration order matches first-occurrence order within `cls.methods`.
    """
    groups: list[list[MethodIR]] = []
    seen: set[int] = set()  # ids of methods already placed

    # Index property partners.
    prop_buckets: dict[str, list[MethodIR]] = defaultdict(list)
    for m in cls.methods:
        for prop_tag in ("nb_prop_ro", "nb_prop_rw"):
            if prop_tag in m.tags.values:
                prop_buckets[m.tags.values[prop_tag]].append(m)

    # Index overload sets among non-property methods.
    overload_buckets: dict[str, list[MethodIR]] = defaultdict(list)
    for m in cls.methods:
        if "nb_prop_ro" in m.tags.values or "nb_prop_rw" in m.tags.values:
            continue
        overload_buckets[_python_name(m)].append(m)

    for m in cls.methods:
        if id(m) in seen:
            continue
        if "nb_prop_ro" in m.tags.values or "nb_prop_rw" in m.tags.values:
            key = m.tags.get("nb_prop_ro") or m.tags.get("nb_prop_rw")
            partners = prop_buckets[key]
            for p in partners:
                seen.add(id(p))
            groups.append(partners)
            continue
        py = _python_name(m)
        bucket = overload_buckets[py]
        if len(bucket) >= 2:
            for p in bucket:
                seen.add(id(p))
            groups.append(bucket)
        else:
            seen.add(id(m))
            groups.append([m])

    return groups


def emit_class(cls: ClassIR) -> str:
    """Render a class head plus all of its grouped method/property/overload defs."""
    head = emit_class_head(cls)
    parts: list[str] = []
    for group in _group_methods(cls):
        if "nb_prop_ro" in group[0].tags.values or "nb_prop_rw" in group[0].tags.values:
            parts.append(emit_property(group, cls.cpp_name))
        elif len(group) >= 2 and not all(_is_init(m, cls.cpp_name) for m in group):
            parts.extend(emit_overload(group, cls.cpp_name))
        else:
            parts.extend(emit_method(m, cls.cpp_name) for m in group)
    body = "".join(f"\n{TAB}{TAB}{p}" for p in parts)
    return f"{TAB}{head}{body};"


def emit_header(header_name: str, header_ir: HeaderIR) -> str:
    """Render the full bind_<name>(nb::module_ &m) translation unit as a string."""
    enum_blocks = [emit_enum(e) for e in header_ir.enums]
    class_blocks = [emit_class(c) for c in header_ir.classes]
    free_blocks = [f"{TAB}{emit_free_function(f)}" for f in header_ir.free_functions]

    enums_section = "\n\n".join(enum_blocks)
    classes_section = "\n\n".join(class_blocks)
    free_section = "\n\n".join(free_blocks)

    return (
        f"#pragma once\n"
        f"// This file was autogenerated. Do not edit. //\n"
        f'#include "{header_name}.h"\n'
        f"\n"
        f"void bind_{header_name.lower()}(nb::module_ &m)\n"
        f"{{\n"
        f"    // Enums\n"
        f"{enums_section}\n"
        f"\n"
        f"    // Classes\n"
        f"{classes_section}\n"
        f"\n"
        f"    // Functions\n"
        f"{free_section}\n"
        f"\n"
        f"}};\n"
    )
