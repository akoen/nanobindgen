import difflib
from pathlib import Path

import nanobindgen


def test_golden():
    here = Path(__file__).parent
    source = (here / "input.h").read_text()
    expected = (here / "expected_output.h").read_text()

    actual = nanobindgen.build_header("input", source)

    if actual != expected:
        diff = "\n".join(
            difflib.unified_diff(
                expected.splitlines(),
                actual.splitlines(),
                fromfile="expected_output.h",
                tofile="actual",
                lineterm="",
            )
        )
        raise AssertionError(f"golden mismatch:\n{diff}")
