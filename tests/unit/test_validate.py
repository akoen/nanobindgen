from nanobindgen.errors import ErrorCollector
from nanobindgen.ir import (
    ClassIR,
    DocIR,
    HeaderIR,
    MethodIR,
    Param,
    SourceLoc,
    TagSet,
)
from nanobindgen.validate import validate


def _ts(flags=(), values=None, repeats=None, locations=None):
    locs = dict(locations or {})
    flags = frozenset(flags)
    values = values or {}
    repeats = {k: tuple(v) for k, v in (repeats or {}).items()}
    if not locs:
        # Auto-fill locations for any tag not already located.
        loc = (SourceLoc("a.h", 1, 1),)
        for f in flags:
            locs.setdefault(f, loc)
        for k in values:
            locs.setdefault(k, loc)
        for k in repeats:
            locs.setdefault(k, loc)
    return TagSet(flags=flags, values=values, repeats=repeats, locations=locs)


def _empty_class(tags):
    return ClassIR(
        cpp_name="C",
        loc=SourceLoc("a.h", 1, 1),
        tags=tags,
        doc=DocIR(),
        methods=(),
    )


def _empty_method(tags, name="m", is_cpp_static=False):
    return MethodIR(
        cpp_name=name,
        loc=SourceLoc("a.h", 2, 1),
        params=(),
        is_cpp_static=is_cpp_static,
        tags=tags,
        doc=DocIR(),
    )


def test_unknown_tag_errors_with_suggestion():
    tags = _ts(flags={"nb"}, values={"nb_prop_r": "foo"})
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(_empty_method(tags),),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    msgs = [e.message for e in collector.errors]
    assert any(
        "unknown tag @nb_prop_r" in m and "did you mean @nb_prop_ro" in m for m in msgs
    )


def test_wrong_target_errors():
    # @nb_inherit on a method (only valid on class)
    tags = _ts(flags={"nb"}, values={"nb_inherit": "Base"})
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(_empty_method(tags),),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "@nb_inherit is not valid on method" in e.message for e in collector.errors
    )


def test_arity_violation_flag_with_body():
    # @nb_static is a flag; if it ended up in 'values' that's a body present.
    tags = _ts(flags={"nb"}, values={"nb_static": "yes"})
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(_empty_method(tags),),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "@nb_static does not take a value" in e.message for e in collector.errors
    )


def test_mutual_exclusion():
    tags = _ts(flags={"nb", "nb_init", "nb_static"})
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(_empty_method(tags, name="C"),),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "@nb_init and @nb_static cannot both be set" in e.message
        or "@nb_static and @nb_init cannot both be set" in e.message
        for e in collector.errors
    )


def test_required_body_missing():
    # @nb_name requires a value; if it appears in flags that's missing-body.
    tags = _ts(flags={"nb", "nb_name"})
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(_empty_method(tags),),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any("@nb_name requires a value" in e.message for e in collector.errors)


def test_bind_marker_without_nb_errors():
    tags = _ts(values={"nb_name": "foo"})  # no "nb" flag
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(_empty_method(tags),),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "@nb_name found but @nb is missing" in e.message for e in collector.errors
    )


def test_property_rw_unpaired_setter_or_getter_errors():
    # One method tagged @nb_prop_rw "name" -> getter or setter missing.
    tags1 = _ts(flags={"nb"}, values={"nb_prop_rw": "name"})
    m1 = MethodIR("get_name", SourceLoc("a.h", 2, 1), (), False, tags1, DocIR())
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C", SourceLoc("a.h", 1, 1), _ts(flags={"nb"}), DocIR(), methods=(m1,)
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        '@nb_prop_rw "name" has a getter but no setter' in e.message
        or '@nb_prop_rw "name" has a setter but no getter' in e.message
        for e in collector.errors
    )


def test_overload_kind_mismatch_errors():
    # Two methods sharing a Python name, one static, one not -> error.
    tags_a = _ts(flags={"nb"})
    tags_b = _ts(flags={"nb", "nb_static"})
    m_a = MethodIR(
        "foo",
        SourceLoc("a.h", 2, 1),
        (Param("int", "x", None),),
        False,
        tags_a,
        DocIR(),
    )
    m_b = MethodIR(
        "foo",
        SourceLoc("a.h", 5, 1),
        (Param("double", "y", None),),
        True,
        tags_b,
        DocIR(),
    )
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C",
                SourceLoc("a.h", 1, 1),
                _ts(flags={"nb"}),
                DocIR(),
                methods=(m_a, m_b),
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "overload" in e.message and "kind" in e.message for e in collector.errors
    )


def test_param_doc_mismatch_warns():
    # @param documents 'q' but signature has 'x' -> warning.
    tags = _ts(flags={"nb"})
    doc = DocIR(params=(("q", "wrong name"),))
    m = MethodIR(
        "foo", SourceLoc("a.h", 2, 1), (Param("int", "x", None),), False, tags, doc
    )
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C", SourceLoc("a.h", 1, 1), _ts(flags={"nb"}), DocIR(), methods=(m,)
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any("@param 'q' does not match" in w.message for w in collector.warnings)
    assert any("parameter 'x' has no @param" in w.message for w in collector.warnings)


def test_nb_doc_with_brief_warns():
    tags = _ts(flags={"nb"}, values={"nb_doc": "override"})
    doc = DocIR(brief="brief tag value", override="override")
    m = MethodIR("foo", SourceLoc("a.h", 2, 1), (), False, tags, doc)
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR(
                "C", SourceLoc("a.h", 1, 1), _ts(flags={"nb"}), DocIR(), methods=(m,)
            ),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "@nb_doc is set; @brief is ignored" in w.message for w in collector.warnings
    )


def test_extra_with_dedicated_intrusive_ptr_warns():
    cls_tags = _ts(
        flags={"nb", "nb_intrusive_ptr"},
        repeats={"nb_extra": ("nb::intrusive_ptr<Foo>([](Foo*, PyObject*){})",)},
    )
    h = HeaderIR(
        "a.h",
        classes=(
            ClassIR("Foo", SourceLoc("a.h", 1, 1), cls_tags, DocIR(), methods=()),
        ),
        free_functions=(),
        enums=(),
    )
    collector = ErrorCollector()
    validate(h, collector)
    assert any(
        "nb::intrusive_ptr" in w.message and "nb_intrusive_ptr" in w.message
        for w in collector.warnings
    )


from pathlib import Path

import pytest

import nanobindgen

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "errors"


@pytest.mark.parametrize(
    "fixture_name,expected_substring",
    [
        ("unknown_tag.h", "unknown tag @nb_prop_r"),
        ("wrong_target.h", "@nb_inherit is not valid on method"),
        ("arity_violation.h", "@nb_static does not take a value"),
        ("mutual_exclusion.h", "cannot both be set"),
        ("required_body.h", "@nb_name requires a value"),
        ("bind_marker_missing.h", "@nb_name found but @nb is missing"),
        ("prop_unpaired.h", '@nb_prop_rw "name"'),
    ],
)
def test_fixture_produces_expected_error(fixture_name, expected_substring):
    source = (FIXTURE_DIR / fixture_name).read_text()
    with pytest.raises(nanobindgen.NanobindgenError) as exc_info:
        nanobindgen.build_header(fixture_name.replace(".h", ""), source)
    assert expected_substring in str(exc_info.value)
