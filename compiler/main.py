#!/usr/bin/env python3
"""Million Compiler CLI."""

import argparse
import sys
from pathlib import Path

from compiler import __version__
from compiler.compile import compile_million, PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="million",
        description="Million Language Compiler — brain-inspired neural computation",
    )
    parser.add_argument("input", nargs="?", help="Input .million file")
    parser.add_argument("output", nargs="?", help="Output file (default: input basename)")
    parser.add_argument("-V", "--version", action="version", version=f"Million {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress status messages")
    parser.add_argument(
        "--repl", action="store_true", help="Launch interactive REPL"
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "c", "llvm"],
        default="auto",
        help="Code backend: auto (default), c, or llvm",
    )
    parser.add_argument(
        "--quantization",
        choices=["f32", "int8", "binary"],
        default="f32",
        help="Quantization mode (default: f32)",
    )
    parser.add_argument(
        "--mode",
        choices=["hybrid", "online"],
        default="hybrid",
        help="Learning mode: hybrid or online (default: hybrid)",
    )
    args = parser.parse_args(argv)

    if args.repl:
        from compiler.repl import run_repl
        run_repl(backend=args.backend, quantization=args.quantization, mode=args.mode)
        return 0

    if not args.input:
        parser.print_help()
        return 1

    source = Path(args.input)
    if not source.is_file():
        print(f"Error: file not found: {source}", file=sys.stderr)
        return 1

    output = Path(args.output) if args.output else source.with_suffix(".c")

    if not args.quiet:
        print(f"Million Compiler v{__version__}")
        print(f"  Source: {source}")
        print(f"  Output: {output}")
        print(f"  Backend: {args.backend}")
        print(f"  Quantization: {args.quantization}")
        print(f"  Mode: {args.mode}")
        print()

    try:
        c_code = compile_million(
            source,
            output,
            search_paths=[PROJECT_ROOT, PROJECT_ROOT / "stdlib"],
            backend=args.backend,
            quantization=args.quantization,
            mode=args.mode,
        )
    except (SyntaxError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Generated {len(c_code)} bytes of C code.")
        print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
