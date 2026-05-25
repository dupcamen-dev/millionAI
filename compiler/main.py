#!/usr/bin/env python3
"""
Million Compiler v0.1
Language for brain-inspired neural computation.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.ir.million_ir import IRBuilder
from compiler.codegen import CCodeGen


def compile_million(source_path: str, output_path: str = None) -> str:
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Lex
    lexer = Lexer(source)
    tokens = lexer.tokenize()

    # Parse
    parser = Parser(tokens)
    ast = parser.parse()

    # Build IR
    builder = IRBuilder()
    mir = builder.build(ast)

    # Codegen
    codegen = CCodeGen(mir)
    c_code = codegen.generate()

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(c_code)

    return c_code


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m compiler.main <input.million> [output.c]")
        sys.exit(1)

    source_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else source_path.rsplit(".", 1)[0] + ".c"

    print(f"Million Compiler v0.1")
    print(f"  Source: {source_path}")
    print(f"  Output: {output_path}")
    print()

    c_code = compile_million(source_path, output_path)
    print(f"Generated {len(c_code)} bytes of C code.")
    print("Done.")


if __name__ == "__main__":
    main()
