"""CLI entry point: nanobindgen -o <out_dir> file1.h file2.h ..."""

import argparse
import sys
from pathlib import Path

from . import build_header
from .errors import NanobindgenError


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate nanobind bindings from C++ headers")
    parser.add_argument(
        "-o", "--output", type=str, required=True,
        help="directory where bind_<name>.h files will be written",
    )
    parser.add_argument("files", metavar="F", type=str, nargs="+", help="header files to process")
    args = parser.parse_args()

    out_dir = Path(args.output.strip())
    exit_code = 0
    for file_path in args.files:
        path = Path(file_path)
        source = path.read_text(encoding="utf-8")
        try:
            code = build_header(path.stem, source)
        except NanobindgenError as e:
            print(str(e), file=sys.stderr)
            exit_code = 1
            continue
        (out_dir / f"bind_{path.stem}.h").write_text(code, encoding="utf-8")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
