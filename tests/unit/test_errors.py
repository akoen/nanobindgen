from nanobindgen.errors import NanobindgenError, ErrorCollector


def test_error_formats_with_source_location():
    err = NanobindgenError("phnx.h", 42, 5, "unknown tag @nb_foo")
    assert str(err) == "phnx.h:42:5: error: unknown tag @nb_foo"


def test_collector_aggregates_errors():
    collector = ErrorCollector()
    collector.error("a.h", 1, 1, "first")
    collector.error("a.h", 2, 1, "second")
    assert collector.errors == [
        NanobindgenError("a.h", 1, 1, "first"),
        NanobindgenError("a.h", 2, 1, "second"),
    ]
    assert collector.has_errors


def test_collector_aggregates_warnings_separately():
    collector = ErrorCollector()
    collector.warning("a.h", 1, 1, "smell")
    assert not collector.has_errors
    assert collector.warnings[0].message == "smell"


def test_collector_format_summary():
    collector = ErrorCollector()
    collector.error("a.h", 1, 1, "first")
    collector.error("a.h", 2, 1, "second")
    assert collector.format_summary() == (
        "a.h:1:1: error: first\n"
        "a.h:2:1: error: second\n"
        "\n"
        "2 errors generated."
    )


def test_collector_raise_if_errors_no_op_when_clean():
    collector = ErrorCollector()
    collector.warning("a.h", 1, 1, "ok")
    collector.raise_if_errors()  # should not raise


def test_collector_raise_if_errors_raises_with_summary():
    collector = ErrorCollector()
    collector.error("a.h", 1, 1, "boom")
    try:
        collector.raise_if_errors()
        raise AssertionError("expected NanobindgenError")
    except NanobindgenError as e:
        assert "a.h:1:1: error: boom" in str(e)
