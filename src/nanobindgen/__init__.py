"""Public API: build_header(name, source) -> str.

Orchestrates parse -> validate -> emit. Errors are aggregated and raised once.
"""

from .errors import ErrorCollector, NanobindgenError
from .emit import emit_header
from .parse import parse_header
from .validate import validate

__all__ = ["build_header", "NanobindgenError"]


def build_header(header_name: str, source_code: str) -> str:
    source_bytes = source_code.encode("utf-8") if isinstance(source_code, str) else source_code
    header_ir = parse_header(f"{header_name}.h", source_bytes)
    collector = ErrorCollector()
    validate(header_ir, collector)
    collector.raise_if_errors()
    return emit_header(header_name, header_ir)
