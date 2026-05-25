"""Tests for type system and control flow."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.parser.ast import *

def test_var_decl():
    src = "let x: int = 42"
    lexer = Lexer(src)
    parser = Parser(lexer.tokenize())
    prog = parser.parse()
    assert len(prog.declarations) == 1
    d = prog.declarations[0]
    assert isinstance(d, VarDecl)
    assert d.name == "x"
    assert d.type.name == "int"
    print("  [ok] test_var_decl")

def test_fn_decl():
    src = "fn add(x: f32, y: f32) -> f32 { return x + y }"
    lexer = Lexer(src)
    parser = Parser(lexer.tokenize())
    prog = parser.parse()
    assert len(prog.declarations) == 1
    d = prog.declarations[0]
    assert isinstance(d, FuncDef)
    assert d.name == "add"
    assert len(d.params) == 2
    print("  [ok] test_fn_decl")

def test_if_stmt():
    src = """
neuron N {
    nucleus: state[8]
    membrane { potential: 0.0 threshold: 1.0 refractory: 0 }
    dynamics {
        if x > 0.0 {
            output = 1.0
        } else {
            output = 0.0
        }
    }
}
region R { neurons: N[1] }
infer R on x { output -> y }
"""
    lexer = Lexer(src)
    parser = Parser(lexer.tokenize())
    prog = parser.parse()
    assert len(prog.declarations) == 3
    print("  [ok] test_if_stmt")

def test_for_stmt():
    src = """
neuron N {
    nucleus: state[4]
    membrane { potential: 0.0 threshold: 1.0 refractory: 0 }
    dynamics {
        sum = 0
        for i in 0..10 {
            sum = sum + i
        }
        output = sum
    }
}
region R { neurons: N[1] }
infer R on x { output -> y }
"""
    lexer = Lexer(src)
    parser = Parser(lexer.tokenize())
    prog = parser.parse()
    assert len(prog.declarations) == 3
    print("  [ok] test_for_stmt")

def test_types_demo():
    from compiler.compile import parse_program, PROJECT_ROOT
    path = PROJECT_ROOT / "examples" / "types_demo.million"
    if path.exists():
        prog = parse_program(path)
        names = [type(d).__name__ for d in prog.declarations]
        assert "FuncDef" in names
        assert "VarDecl" in names
        assert "NeuronDef" in names
        print("  [ok] test_types_demo")

def test_tensor_type():
    src = 'let data: tensor[28, 28]'
    lexer = Lexer(src)
    parser = Parser(lexer.tokenize())
    prog = parser.parse()
    assert len(prog.declarations) == 1
    print("  [ok] test_tensor_type")

if __name__ == "__main__":
    print("Running type system tests...")
    test_var_decl()
    test_fn_decl()
    test_if_stmt()
    test_for_stmt()
    test_tensor_type()
    test_types_demo()
    print("All type system tests passed!")
