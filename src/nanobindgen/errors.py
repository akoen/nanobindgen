"""Error and warning collection with source-location awareness."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NanobindgenError(Exception):
    """A diagnostic error tied to a source location."""

    path: str
    line: int
    col: int
    message: str

    def __str__(self) -> str:
        """Render as `path:line:col: error: message`."""
        return f"{self.path}:{self.line}:{self.col}: error: {self.message}"


@dataclass(frozen=True)
class NanobindgenWarning:
    """A non-fatal diagnostic tied to a source location."""

    path: str
    line: int
    col: int
    message: str

    def __str__(self) -> str:
        """Render as `path:line:col: warning: message`."""
        return f"{self.path}:{self.line}:{self.col}: warning: {self.message}"


@dataclass
class ErrorCollector:
    """Accumulates errors and warnings during validation."""

    errors: list[NanobindgenError] = field(default_factory=list)
    warnings: list[NanobindgenWarning] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """True if any errors have been recorded."""
        return bool(self.errors)

    def error(self, path: str, line: int, col: int, message: str) -> None:
        """Record an error at the given location."""
        self.errors.append(NanobindgenError(path, line, col, message))

    def warning(self, path: str, line: int, col: int, message: str) -> None:
        """Record a warning at the given location."""
        self.warnings.append(NanobindgenWarning(path, line, col, message))

    def format_summary(self) -> str:
        """Render all errors and warnings as a single multi-line string."""
        lines = [str(e) for e in self.errors] + [str(w) for w in self.warnings]
        if self.errors:
            n = len(self.errors)
            lines.append("")
            lines.append(f"{n} error{'s' if n != 1 else ''} generated.")
        return "\n".join(lines)

    def raise_if_errors(self) -> None:
        """Raise NanobindgenError carrying the full summary if any errors occurred."""
        if self.has_errors:
            raise NanobindgenError(
                self.errors[0].path,
                self.errors[0].line,
                self.errors[0].col,
                self.format_summary(),
            )
