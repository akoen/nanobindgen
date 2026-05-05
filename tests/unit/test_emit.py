from nanobindgen.emit import (
    emit_class,
    emit_class_head,
    emit_method,
    emit_property,
    emit_overload,
    emit_free_function,
    emit_enum,
    emit_header,
    gen_docstring,
    raw_string,
)
from nanobindgen.ir import (
    ClassIR,
    DocIR,
    MethodIR,
    Param,
    SourceLoc,
    TagSet,
    EnumIR,
    EnumValueIR,
    FreeFunctionIR,
    HeaderIR,
)


def test_raw_string_simple():
    assert raw_string("hello") == 'R"nbdoc(hello)nbdoc"'


def test_raw_string_with_quotes_and_backslashes():
    s = 'a "quote" and a \\ backslash'
    assert raw_string(s) == 'R"nbdoc(a "quote" and a \\ backslash)nbdoc"'


def test_raw_string_falls_back_when_delimiter_collides():
    s = 'evil )nbdoc" content'
    out = raw_string(s)
    assert out.startswith('R"')
    assert out.endswith('"')
    # Whatever delimiter is chosen, the original content survives unaltered.
    assert s in out


def test_gen_docstring_brief_only():
    doc = DocIR(brief="A short brief.")
    assert gen_docstring(doc) == "A short brief."


def test_gen_docstring_with_args_returns_raises():
    doc = DocIR(
        brief="Hi.",
        params=(("x", "the x value"), ("y", "the y value")),
        returns="the result",
        raises=(("ValueError", "on bad input"),),
    )
    out = gen_docstring(doc)
    assert "Hi." in out
    assert "Args:\n    x: the x value\n    y: the y value" in out
    assert "Returns:\n    the result" in out
    assert "Raises:\n    ValueError: on bad input" in out


def test_gen_docstring_override_short_circuits():
    doc = DocIR(brief="ignored", override="custom doc")
    assert gen_docstring(doc) == "custom doc"


def test_gen_docstring_with_detail_paragraph():
    doc = DocIR(brief="Brief.", detail="Detail paragraph.")
    out = gen_docstring(doc)
    assert out.startswith("Brief.")
    assert "Detail paragraph." in out


def _cls(tags: TagSet, doc: DocIR = DocIR(), name: str = "Foo") -> ClassIR:
    return ClassIR(
        cpp_name=name,
        loc=SourceLoc("a.h", 1, 1),
        tags=tags,
        doc=doc,
        methods=(),
    )


def test_emit_class_head_minimal():
    out = emit_class_head(_cls(TagSet(flags=frozenset({"nb"}))))
    assert out == 'nb::class_<Foo>(m, "Foo")'


def test_emit_class_head_with_inherit():
    tags = TagSet(flags=frozenset({"nb"}), repeats={"nb_inherit": ("Base",)})
    out = emit_class_head(_cls(tags))
    assert out == 'nb::class_<Foo, Base>(m, "Foo")'


def test_emit_class_head_with_multiple_inherits():
    tags = TagSet(flags=frozenset({"nb"}), repeats={"nb_inherit": ("Base1", "Base2")})
    out = emit_class_head(_cls(tags))
    assert out == 'nb::class_<Foo, Base1, Base2>(m, "Foo")'


def test_emit_class_head_with_name_override():
    tags = TagSet(flags=frozenset({"nb"}), values={"nb_name": "PyFoo"})
    out = emit_class_head(_cls(tags))
    assert out == 'nb::class_<Foo>(m, "PyFoo")'


def test_emit_class_head_with_intrusive_ptr():
    tags = TagSet(flags=frozenset({"nb", "nb_intrusive_ptr"}))
    out = emit_class_head(_cls(tags))
    assert out == (
        'nb::class_<Foo>(m, "Foo", '
        'nb::intrusive_ptr<Foo>([](Foo* o, PyObject* po) noexcept '
        '{ o->set_self_py(po); }))'
    )


def test_emit_class_head_with_policy_flags():
    tags = TagSet(flags=frozenset({"nb", "nb_dynamic_attr", "nb_final", "nb_weak_ref"}))
    out = emit_class_head(_cls(tags))
    assert "nb::dynamic_attr()" in out
    assert "nb::is_final()" in out
    assert "nb::is_weak_referenceable()" in out


def test_emit_class_head_with_extras():
    tags = TagSet(
        flags=frozenset({"nb"}),
        repeats={"nb_extra": ("nb::sig(\"sig\")", "nb::raw_doc(\"d\")")},
    )
    out = emit_class_head(_cls(tags))
    assert 'nb::sig("sig")' in out
    assert 'nb::raw_doc("d")' in out


def test_emit_class_head_with_docstring():
    doc = DocIR(brief="A class.")
    tags = TagSet(flags=frozenset({"nb"}))
    out = emit_class_head(_cls(tags, doc))
    assert 'R"nbdoc(A class.)nbdoc"' in out


def _method(
    cpp_name="bar",
    params=(),
    is_cpp_static=False,
    flags=frozenset({"nb"}),
    values=None,
    repeats=None,
    doc=DocIR(),
):
    return MethodIR(
        cpp_name=cpp_name,
        loc=SourceLoc("a.h", 2, 1),
        params=params,
        is_cpp_static=is_cpp_static,
        tags=TagSet(flags=flags, values=values or {}, repeats={k: tuple(v) for k, v in (repeats or {}).items()}),
        doc=doc,
    )


def test_emit_plain_method():
    m = _method(params=(Param("int", "x", None),))
    out = emit_method(m, class_name="C")
    assert out == '.def("bar", &C::bar, "x"_a)'


def test_emit_method_with_default_arg():
    m = _method(params=(Param("int", "x", "0"),))
    out = emit_method(m, class_name="C")
    assert out == '.def("bar", &C::bar, "x"_a = 0)'


def test_emit_static_method_via_cpp_keyword():
    m = _method(is_cpp_static=True)
    out = emit_method(m, class_name="C")
    assert out == '.def_static("bar", &C::bar)'


def test_emit_static_method_via_explicit_tag():
    m = _method(flags=frozenset({"nb", "nb_static"}))
    out = emit_method(m, class_name="C")
    assert out == '.def_static("bar", &C::bar)'


def test_emit_init_via_method_name_match():
    m = _method(cpp_name="C", params=(Param("int", "x", None),))
    out = emit_method(m, class_name="C")
    assert out == '.def(nb::init<int>(), "x"_a)'


def test_emit_init_via_explicit_tag():
    m = _method(cpp_name="ctor", flags=frozenset({"nb", "nb_init"}), params=(Param("int", "x", None),))
    out = emit_method(m, class_name="C")
    assert out == '.def(nb::init<int>(), "x"_a)'


def test_emit_new_factory():
    m = _method(cpp_name="make", params=(Param("int", "x", None),), flags=frozenset({"nb", "nb_new"}))
    out = emit_method(m, class_name="C")
    assert out == '.def(nb::new_(&C::make), "x"_a)'


def test_emit_method_with_name_override():
    m = _method(values={"nb_name": "__iter__"})
    out = emit_method(m, class_name="C")
    assert out.startswith('.def("__iter__", &C::bar')


def test_emit_method_with_docstring_and_extras():
    doc = DocIR(brief="Hi.")
    m = _method(
        params=(Param("int", "x", None),),
        repeats={"nb_extra": ("nb::keep_alive<0, 1>()",)},
        doc=doc,
    )
    out = emit_method(m, class_name="C")
    assert 'R"nbdoc(Hi.)nbdoc"' in out
    assert "nb::keep_alive<0, 1>()" in out


def test_emit_method_with_sig():
    m = _method(values={"nb_sig": "(self, x: int) -> None"})
    out = emit_method(m, class_name="C")
    assert 'nb::sig("(self, x: int) -> None")' in out




def test_emit_prop_ro():
    m = _method(cpp_name="get_name", values={"nb_prop_ro": "name"})
    out = emit_property([m], class_name="C")
    assert out == '.def_prop_ro("name", &C::get_name)'


def test_emit_prop_ro_static():
    m = _method(cpp_name="get_kind", values={"nb_prop_ro": "kind"}, flags=frozenset({"nb", "nb_static"}))
    out = emit_property([m], class_name="C")
    assert out == '.def_prop_ro_static("kind", &C::get_kind)'


def test_emit_prop_rw():
    g = _method(cpp_name="get_name", values={"nb_prop_rw": "name"})
    s = _method(
        cpp_name="set_name",
        values={"nb_prop_rw": "name"},
        params=(Param("std::string", "v", None),),
    )
    out = emit_property([g, s], class_name="C")
    assert out == '.def_prop_rw("name", &C::get_name, &C::set_name)'


def test_emit_prop_rw_with_docstring_from_getter():
    g = _method(cpp_name="get_name", values={"nb_prop_rw": "name"}, doc=DocIR(brief="Name."))
    s = _method(
        cpp_name="set_name",
        values={"nb_prop_rw": "name"},
        params=(Param("std::string", "v", None),),
    )
    out = emit_property([g, s], class_name="C")
    assert 'R"nbdoc(Name.)nbdoc"' in out


def test_emit_overload():
    a = _method(cpp_name="foo", params=(Param("int", "x", None),))
    b = _method(cpp_name="foo", params=(Param("double", "y", None),))
    parts = emit_overload([a, b], class_name="C")
    assert parts == [
        '.def("foo", nb::overload_cast<int>(&C::foo), "x"_a)',
        '.def("foo", nb::overload_cast<double>(&C::foo), "y"_a)',
    ]




def test_emit_free_function():
    fn = FreeFunctionIR(
        cpp_name="foo",
        loc=SourceLoc("a.h", 1, 1),
        params=(Param("int", "x", None),),
        tags=TagSet(flags=frozenset({"nb"})),
        doc=DocIR(),
    )
    out = emit_free_function(fn)
    assert out == 'm.def("foo", &foo, "x"_a);'


def test_emit_free_function_with_doc_and_extras():
    fn = FreeFunctionIR(
        cpp_name="foo",
        loc=SourceLoc("a.h", 1, 1),
        params=(),
        tags=TagSet(
            flags=frozenset({"nb"}),
            repeats={"nb_extra": ("nb::call_guard<nb::gil_scoped_release>()",)},
        ),
        doc=DocIR(brief="Hi."),
    )
    out = emit_free_function(fn)
    assert 'R"nbdoc(Hi.)nbdoc"' in out
    assert "nb::call_guard<nb::gil_scoped_release>()" in out


def test_emit_enum_basic():
    e = EnumIR(
        cpp_name="Color",
        loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb"})),
        doc=DocIR(),
        values=(
            EnumValueIR("RED", None, DocIR(), SourceLoc("a.h", 2, 1)),
            EnumValueIR("BLUE", None, DocIR(), SourceLoc("a.h", 3, 1)),
        ),
    )
    out = emit_enum(e)
    assert 'nb::enum_<Color>(m, "Color")' in out
    assert '.value("RED", Color::RED)' in out
    assert '.value("BLUE", Color::BLUE)' in out


def test_emit_enum_with_value_docstrings():
    e = EnumIR(
        cpp_name="C",
        loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb"})),
        doc=DocIR(),
        values=(
            EnumValueIR("A", None, DocIR(brief="The A."), SourceLoc("a.h", 2, 1)),
        ),
    )
    out = emit_enum(e)
    assert '.value("A", C::A, R"nbdoc(The A.)nbdoc")' in out


def test_emit_enum_with_arithmetic_and_flag_and_doc():
    e = EnumIR(
        cpp_name="F",
        loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb", "nb_arithmetic", "nb_flag"})),
        doc=DocIR(brief="Flags."),
        values=(EnumValueIR("X", None, DocIR(), SourceLoc("a.h", 2, 1)),),
    )
    out = emit_enum(e)
    assert "nb::is_arithmetic()" in out
    assert "nb::is_flag()" in out
    assert 'R"nbdoc(Flags.)nbdoc"' in out


def test_emit_class_groups_property_pair():
    g = _method(cpp_name="get_name", values={"nb_prop_rw": "name"})
    s = _method(
        cpp_name="set_name",
        values={"nb_prop_rw": "name"},
        params=(Param("std::string", "v", None),),
    )
    cls = ClassIR(
        cpp_name="C", loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb"})), doc=DocIR(), methods=(g, s),
    )
    out = emit_class(cls)
    assert '.def_prop_rw("name", &C::get_name, &C::set_name)' in out
    assert out.endswith(";")


def test_emit_class_groups_overloads():
    a = _method(cpp_name="foo", params=(Param("int", "x", None),))
    b = _method(cpp_name="foo", params=(Param("double", "y", None),))
    cls = ClassIR(
        cpp_name="C", loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb"})), doc=DocIR(), methods=(a, b),
    )
    out = emit_class(cls)
    assert "nb::overload_cast<int>" in out
    assert "nb::overload_cast<double>" in out


def test_emit_header_combines_classes_enums_free_functions():
    cls = ClassIR(
        cpp_name="C", loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb"})), doc=DocIR(), methods=(),
    )
    fn = FreeFunctionIR(
        cpp_name="foo", loc=SourceLoc("a.h", 1, 1), params=(),
        tags=TagSet(flags=frozenset({"nb"})), doc=DocIR(),
    )
    enum = EnumIR(
        cpp_name="E", loc=SourceLoc("a.h", 1, 1),
        tags=TagSet(flags=frozenset({"nb"})), doc=DocIR(),
        values=(EnumValueIR("X", None, DocIR(), SourceLoc("a.h", 2, 1)),),
    )
    h = HeaderIR("a.h", classes=(cls,), free_functions=(fn,), enums=(enum,))
    out = emit_header("input", h)
    assert "#pragma once" in out
    assert '#include "input.h"' in out
    assert "void bind_input(nb::module_ &m)" in out
    assert "nb::class_<C>" in out
    assert "nb::enum_<E>" in out
    assert 'm.def("foo"' in out
