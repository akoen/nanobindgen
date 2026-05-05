from nanobindgen.parse import (
    extract_doc_from_comment,
    extract_tagset_from_comment,
    parse_cpp,
    parse_header,
)


def _comment_node(src: bytes):
    """Parse a C++ snippet and return its first comment node."""
    tree = parse_cpp(src)
    for child in tree.root_node.children:
        if child.type == "comment":
            return child
    raise AssertionError("no comment found")


def test_extract_bare_nb_marker():
    src = b"""/**
 * Foo.
 * @nb
 */
"""
    comment = _comment_node(src)
    ts = extract_tagset_from_comment(comment, path="a.h")
    assert "nb" in ts.flags


def test_extract_nb_name_value():
    src = b"""/**
 * @nb
 * @nb_name __iter__
 */
"""
    comment = _comment_node(src)
    ts = extract_tagset_from_comment(comment, path="a.h")
    assert ts.get("nb_name") == "__iter__"


def test_extract_repeatable_extra():
    src = b"""/**
 * @nb
 * @nb_extra nb::keep_alive<0, 1>()
 * @nb_extra nb::call_guard<nb::gil_scoped_release>()
 */
"""
    comment = _comment_node(src)
    ts = extract_tagset_from_comment(comment, path="a.h")
    assert ts.get_all("nb_extra") == (
        "nb::keep_alive<0, 1>()",
        "nb::call_guard<nb::gil_scoped_release>()",
    )


def test_extract_intrusive_ptr_flag():
    src = b"""/**
 * @nb
 * @nb_intrusive_ptr
 */
"""
    comment = _comment_node(src)
    ts = extract_tagset_from_comment(comment, path="a.h")
    assert "nb_intrusive_ptr" in ts.flags


def test_extract_records_source_locations():
    src = b"""/**
 * @nb
 * @nb_name Foo
 */
"""
    comment = _comment_node(src)
    ts = extract_tagset_from_comment(comment, path="a.h")
    assert "nb_name" in ts.locations
    locs = ts.locations["nb_name"]
    assert len(locs) >= 1
    loc = locs[0]
    assert loc.path == "a.h"
    assert loc.line >= 1


def test_extract_ignores_non_nb_doxygen_tags():
    src = b"""/**
 * @brief A brief
 * @param x The x param
 * @nb
 */
"""
    comment = _comment_node(src)
    ts = extract_tagset_from_comment(comment, path="a.h")
    # @brief and @param are doc tags, not @nb_* tags.
    assert "brief" not in ts.flags
    assert "param" not in ts.flags
    assert "nb" in ts.flags


def test_extract_doc_brief_from_description():
    src = b"""/**
 * A brief.
 * @nb
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.brief == "A brief."


def test_extract_doc_brief_tag_takes_precedence_over_description():
    src = b"""/**
 * Free description.
 * @brief Explicit brief.
 * @nb
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.brief == "Explicit brief."
    assert "Free description." in doc.detail


def test_extract_doc_params():
    src = b"""/**
 * Hi.
 * @param x The x value
 * @param y The y value
 * @nb
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.params == (("x", "The x value"), ("y", "The y value"))


def test_extract_doc_returns_supports_both_spellings():
    src1 = b"""/**
 * @return The result.
 * @nb
 */
"""
    src2 = b"""/**
 * @returns The result.
 * @nb
 */
"""
    for src in (src1, src2):
        comment = _comment_node(src)
        assert extract_doc_from_comment(comment).returns == "The result."


def test_extract_doc_raises_collects_throws_raises_exception():
    src = b"""/**
 * @throws RuntimeError when it breaks.
 * @raises ValueError on bad input.
 * @exception KeyError missing key.
 * @nb
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.raises == (
        ("RuntimeError", "when it breaks."),
        ("ValueError", "on bad input."),
        ("KeyError", "missing key."),
    )


def test_extract_doc_override_from_nb_doc():
    src = b"""/**
 * Original brief.
 * @nb
 * @nb_doc Custom Python docstring.
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.override == "Custom Python docstring."


def test_extract_doc_bare_nb_doc_flag_is_none():
    src = b"""/**
 * @nb
 * @nb_doc
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.override is None


def test_extract_doc_brief_and_nb_doc_both_populate_independently():
    src = b"""/**
 * @brief Source brief.
 * @nb
 * @nb_doc Override text.
 */
"""
    comment = _comment_node(src)
    doc = extract_doc_from_comment(comment)
    assert doc.brief == "Source brief."
    assert doc.override == "Override text."


def test_parse_simple_class():
    src = b"""/**
 * @nb
 */
class Foo
{
};
"""
    h = parse_header("a.h", src)
    assert len(h.classes) == 1
    assert h.classes[0].cpp_name == "Foo"
    assert "nb" in h.classes[0].tags.flags


def test_parse_class_skips_unmarked():
    src = b"""/**
 * Just docs.
 */
class NotBound
{
};
"""
    h = parse_header("a.h", src)
    assert h.classes == ()


def test_parse_class_doc_extracted():
    src = b"""/**
 * @brief A class.
 * @nb
 */
class Foo
{
};
"""
    h = parse_header("a.h", src)
    assert h.classes[0].doc.brief == "A class."


def test_parse_class_records_loc():
    src = b"""// preamble
/**
 * @nb
 */
class Foo
{
};
"""
    h = parse_header("a.h", src)
    loc = h.classes[0].loc
    assert loc.path == "a.h"
    assert loc.line == 2  # comment starts on line 2


def test_parse_method_within_class():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * @nb
     */
    int bar(double x);
};
"""
    h = parse_header("a.h", src)
    methods = h.classes[0].methods
    assert len(methods) == 1
    m = methods[0]
    assert m.cpp_name == "bar"
    assert m.is_cpp_static is False
    assert len(m.params) == 1
    assert m.params[0].type == "double"
    assert m.params[0].name == "x"


def test_parse_method_detects_static_keyword():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * @nb
     */
    static int bar();
};
"""
    h = parse_header("a.h", src)
    assert h.classes[0].methods[0].is_cpp_static is True


def test_parse_method_with_default_param():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * @nb
     */
    void bar(int x = 0);
};
"""
    h = parse_header("a.h", src)
    p = h.classes[0].methods[0].params[0]
    assert p.default == "0"


def test_parse_method_skips_unmarked():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * Not bound.
     */
    int bar();

    /**
     * @nb
     */
    int baz();
};
"""
    h = parse_header("a.h", src)
    names = [m.cpp_name for m in h.classes[0].methods]
    assert names == ["baz"]


def test_parse_constructor():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * @nb
     */
    Foo(int x);
};
"""
    h = parse_header("a.h", src)
    m = h.classes[0].methods[0]
    assert m.cpp_name == "Foo"
    assert m.params[0].name == "x"


def test_parse_param_preserves_const_qualifier():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * @nb
     */
    void bar(const int &x);
};
"""
    h = parse_header("a.h", src)
    p = h.classes[0].methods[0].params[0]
    assert p.name == "x"
    assert "const" in p.type
    assert "&" in p.type


def test_parse_param_preserves_sized_type():
    src = b"""/**
 * @nb
 */
class Foo
{
public:
    /**
     * @nb
     */
    void bar(unsigned int x, long long y);
};
"""
    h = parse_header("a.h", src)
    params = h.classes[0].methods[0].params
    assert len(params) == 2
    assert params[0].name == "x"
    assert "unsigned" in params[0].type
    assert params[1].name == "y"
    assert "long" in params[1].type


def test_parse_free_function():
    src = b"""/**
 * @nb
 */
int foo(int x);
"""
    h = parse_header("a.h", src)
    assert len(h.free_functions) == 1
    f = h.free_functions[0]
    assert f.cpp_name == "foo"
    assert f.params[0].name == "x"


def test_parse_free_function_skips_unmarked():
    src = b"""/**
 * Just docs.
 */
int foo();
"""
    h = parse_header("a.h", src)
    assert h.free_functions == ()


def test_parse_enum_basic():
    src = b"""/**
 * @nb
 */
enum class Color
{
    RED,
    GREEN,
    BLUE
};
"""
    h = parse_header("a.h", src)
    assert len(h.enums) == 1
    e = h.enums[0]
    assert e.cpp_name == "Color"
    assert [v.cpp_name for v in e.values] == ["RED", "GREEN", "BLUE"]
    assert all(v.value is None for v in e.values)


def test_parse_enum_with_explicit_values():
    src = b"""/**
 * @nb
 */
enum class E
{
    A = 1,
    B = 2
};
"""
    h = parse_header("a.h", src)
    assert [(v.cpp_name, v.value) for v in h.enums[0].values] == [
        ("A", "1"),
        ("B", "2"),
    ]


def test_parse_enum_value_docstrings():
    src = b"""/**
 * @nb
 */
enum class E
{
    /**
     * @brief First value.
     */
    A,
    /**
     * @brief Second value.
     */
    B
};
"""
    h = parse_header("a.h", src)
    docs = [v.doc.brief for v in h.enums[0].values]
    assert docs == ["First value.", "Second value."]


def test_parse_enum_skips_unmarked():
    src = b"""/**
 * Nope.
 */
enum class E
{
    A
};
"""
    h = parse_header("a.h", src)
    assert h.enums == ()


def test_parse_enum_value_is_bare_identifier():
    src = b"""/**
 * @nb
 */
enum class E
{
    OTHER = 1,
    ALIAS = OTHER
};
"""
    h = parse_header("a.h", src)
    values = h.enums[0].values
    assert (values[0].cpp_name, values[0].value) == ("OTHER", "1")
    assert (values[1].cpp_name, values[1].value) == ("ALIAS", "OTHER")
