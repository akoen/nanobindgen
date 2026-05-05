import pytest

from nanobindgen.ir import (
    ClassIR,
    DocIR,
    HeaderIR,
    MethodIR,
    Param,
    SourceLoc,
    TagSet,
)


def test_source_loc_is_frozen():
    loc = SourceLoc("a.h", 1, 1)
    with pytest.raises(Exception):
        loc.line = 2


def test_param_construction():
    p = Param(type="int", name="x", default=None)
    assert p.name == "x"


def test_tagset_default_is_empty():
    ts = TagSet()
    assert ts.flags == frozenset()
    assert ts.values == {}
    assert ts.repeats == {}
    assert ts.locations == {}


def test_tagset_has_helpers():
    ts = TagSet(flags=frozenset({"nb"}), values={"nb_name": "Foo"})
    assert ts.has("nb")
    assert ts.get("nb_name") == "Foo"
    assert ts.get("nb_doc") is None


def test_tagset_locations_are_tuples_for_multi_occurrence():
    loc1 = SourceLoc("a.h", 1, 1)
    loc2 = SourceLoc("a.h", 5, 1)
    ts = TagSet(locations={"nb_name": (loc1, loc2)})
    assert ts.locations["nb_name"] == (loc1, loc2)
    assert ts.first_loc("nb_name") == loc1
    assert ts.first_loc("nb_doc") is None


def test_tagset_mapping_fields_are_read_only():
    ts = TagSet(values={"nb_name": "Foo"})
    with pytest.raises(TypeError):
        ts.values["x"] = "y"
    with pytest.raises(TypeError):
        ts.repeats["x"] = ()
    with pytest.raises(TypeError):
        ts.locations["x"] = ()


def test_doc_ir_defaults():
    doc = DocIR()
    assert doc.brief == ""
    assert doc.detail == ""
    assert doc.params == ()
    assert doc.returns == ""
    assert doc.raises == ()
    assert doc.override is None


def test_method_ir_construction():
    loc = SourceLoc("a.h", 1, 1)
    m = MethodIR(
        cpp_name="foo",
        loc=loc,
        params=(Param("int", "x", None),),
        is_cpp_static=False,
        tags=TagSet(flags=frozenset({"nb"})),
        doc=DocIR(brief="hi"),
    )
    assert m.cpp_name == "foo"
    assert m.params[0].name == "x"


def test_class_ir_holds_methods_and_loc():
    loc = SourceLoc("a.h", 1, 1)
    c = ClassIR(cpp_name="C", loc=loc, tags=TagSet(), doc=DocIR(), methods=())
    assert c.methods == ()


def test_header_ir_is_a_collection():
    h = HeaderIR(path="a.h", classes=(), free_functions=(), enums=())
    assert h.path == "a.h"
