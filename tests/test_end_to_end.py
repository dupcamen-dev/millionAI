#!/usr/bin/env python3
"""End-to-end test: Million source в†’ C code."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.ir.million_ir import IRBuilder
from compiler.codegen import CCodeGen


def test_full_compilation():
    source = open("examples/chat_neuron.million").read()

    lexer = Lexer(source)
    tokens = lexer.tokenize()
    assert len(tokens) > 20, "Too few tokens"

    parser = Parser(tokens)
    ast = parser.parse()
    assert len(ast.declarations) == 5

    builder = IRBuilder()
    mir = builder.build(ast)
    assert len(mir.neurons) == 1
    assert len(mir.regions) == 1
    assert len(mir.datasets) == 1
    assert len(mir.train_stmts) == 1
    assert len(mir.infer_stmts) == 1

    codegen = CCodeGen(mir)
    c_code = codegen.generate()
    assert len(c_code) > 1000
    assert "#include <stdlib.h>" in c_code
    assert "int main()" in c_code
    assert "process_DNA" in c_code
    assert "infer_Cortex" in c_code

    print("  вњ“ test_full_compilation")


def test_archive_code():
    """Verify archive operations are generated correctly."""
    source = """
neuron Test {
    nucleus: archive{state[8], 2}
    membrane {
        potential: 0.0
        threshold: 1.0
        refractory: 0
    }
    dynamics {
        output = compress(unfold(nucleus, 1))
    }
}
region TestRegion {
    neurons: Test[10]
}
infer TestRegion on x {
    output -> y
}
"""
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    builder = IRBuilder()
    mir = builder.build(ast)
    codegen = CCodeGen(mir)
    c_code = codegen.generate()

    assert "archive_unfold" in c_code
    assert "archive_compress" in c_code
    assert "void process_Test" in c_code
    assert "infer_TestRegion" in c_code
    print("  вњ“ test_archive_code")


if __name__ == "__main__":
    print("Running end-to-end tests...")
    test_full_compilation()
    test_archive_code()
    print("All end-to-end tests passed!")
