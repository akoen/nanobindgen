"""Error and warning collection with source-location awareness."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NanobindgenError(Exception):
    path: str
    line: int
    col: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: error: {self.message}"


@dataclass(frozen=True)
class NanobindgenWarning:
    path: str
    line: int
    col: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: warning: {self.message}"


@dataclass
class ErrorCollector:
    errors: list[NanobindgenError] = field(default_factory=list)
    warnings: list[NanobindgenWarning] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def error(self, path: str, line: int, col: int, message: str) -> None:
        self.errors.append(NanobindgenError(path, line, col, message))

    def warning(self, path: str, line: int, col: int, message: str) -> None:
        self.warnings.append(NanobindgenWarning(path, line, col, message))

    def format_summary(self) -> str:
        lines = [str(e) for e in self.errors] + [str(w) for w in self.warnings]
        if self.errors:
            n = len(self.errors)
            lines.append("")
            lines.append(f"{n} error{'s' if n != 1 else ''} generated.")
        return "\n".join(lines)

    def raise_if_errors(self) -> None:
        if self.has_errors:
            raise NanobindgenError(
                self.errors[0].path,
                self.errors[0].line,
                self.errors[0].col,
                self.format_summary(),
            )
