from nanobindgen.tags import TAG_SCHEMA, TARGETS


def test_every_tag_has_non_empty_target():
    for name, tag in TAG_SCHEMA.items():
        assert tag.target, f"{name} has empty target set"
        assert tag.target <= TARGETS, f"{name} has unknown target(s)"


def test_arity_is_valid():
    valid = {"flag", "once", "repeatable"}
    for name, tag in TAG_SCHEMA.items():
        assert tag.arity in valid, f"{name} has invalid arity {tag.arity!r}"


def test_flag_arity_means_no_value():
    for name, tag in TAG_SCHEMA.items():
        if tag.arity == "flag":
            assert not tag.takes_value, f"flag tag {name} should not take a value"
        else:
            assert tag.takes_value, f"non-flag tag {name} should take a value"


def test_excludes_is_symmetric():
    for a_name, a in TAG_SCHEMA.items():
        for b_name in a.excludes:
            assert b_name in TAG_SCHEMA, f"{a_name} excludes unknown tag {b_name}"
            b = TAG_SCHEMA[b_name]
            assert a_name in b.excludes, (
                f"asymmetric excludes: {a_name} excludes {b_name} "
                f"but {b_name} does not exclude {a_name}"
            )


def test_required_tags_present():
    expected = {
        "nb",
        "nb_name",
        "nb_inherit",
        "nb_intrusive_ptr",
        "nb_dynamic_attr",
        "nb_final",
        "nb_weak_ref",
        "nb_static",
        "nb_init",
        "nb_new",
        "nb_prop_ro",
        "nb_prop_rw",
        "nb_extra",
        "nb_sig",
        "nb_doc",
        "nb_arithmetic",
        "nb_flag",
    }
    assert expected <= set(TAG_SCHEMA.keys())


def test_property_tags_exclude_kind_tags():
    prop_ro = TAG_SCHEMA["nb_prop_ro"]
    assert {"nb_init", "nb_new", "nb_prop_rw", "nb_name"} <= prop_ro.excludes


def test_static_excludes_init_and_new():
    assert {"nb_init", "nb_new"} <= TAG_SCHEMA["nb_static"].excludes
