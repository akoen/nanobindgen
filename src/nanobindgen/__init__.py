"""Public API: build_header(name, source) -> str.

Orchestrates parse -> validate -> emit. Errors are aggregated and raised once.
"""

from .emit import emit_header
from .errors import ErrorCollector, NanobindgenError
from .parse import parse_header
from .validate import validate

__all__ = ["NanobindgenError", "build_header"]


def build_header(header_name: str, source_code: str) -> str:
    """Generate nanobind binding code for a single C++ header.

    Args:
        header_name: stem used for `#include "<name>.h"` and `bind_<name>(...)`.
        source_code: raw C++ source as str or bytes.

    Returns:
        The generated binding header as a string.

    Raises:
        NanobindgenError: aggregated diagnostics if validation fails.
    """
    source_bytes = (
        source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    )
    header_ir = parse_header(f"{header_name}.h", source_bytes)
    collector = ErrorCollector()
    validate(header_ir, collector)
    collector.raise_if_errors()
    return emit_header(header_name, header_ir)
