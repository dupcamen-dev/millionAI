"""Tests for function parsing and codegen."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, PROJECT_ROOT

def test_fn_in_c_codegen():
    c = compile_million(PROJECT_ROOT / "examples" / "types_demo.million", backend="c")
    assert "float add(float x, float y)" in c
    assert "return" in c
    print("  [ok] test_fn_in_c_codegen")

def test_fn_parsed():
    from compiler.lexer import Lexer
    from compiler.parser import Parser
    src = "fn mul(a: f32, b: f32) -> f32 { return a * b }"
    lexer = Lexer(src)
    parser = Parser(lexer.tokenize())
    prog = parser.parse()
    assert len(prog.declarations) == 1
    print("  [ok] test_fn_parsed")

if __name__ == "__main__":
    print("Running function tests...")
    test_fn_parsed()
    test_fn_in_c_codegen()
    print("All function tests passed!")
