#!/usr/bin/env python3
"""Tests for the Million parser."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.parser.ast import *


def parse_source(source: str):
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    return parser.parse()


def test_empty():
    prog = parse_source("")
    assert len(prog.declarations) == 0
    print("  [ok] test_empty")


def test_neuron_minimal():
    source = """
neuron DNA {
    nucleus: archive{state[16], 3}
    membrane {
        potential: 0.0
        threshold: adaptive
        refractory: 1
    }
    dynamics {
        output = process(nucleus, input)
    }
}
"""
    prog = parse_source(source)
    assert len(prog.declarations) == 1
    n = prog.declarations[0]
    assert isinstance(n, NeuronDef)
    assert n.name == "DNA"
    assert n.membrane
    assert n.dynamics
    print("  [ok] test_neuron_minimal")


def test_region():
    source = """
region VisualCortex {
    neurons: LIF[1000]
    connect self -> self: sparse(0.01) {
        plasticity: STDP
    }
}
"""
    prog = parse_source(source)
    assert len(prog.declarations) == 1
    r = prog.declarations[0]
    assert isinstance(r, RegionDef)
    assert r.name == "VisualCortex"
    assert r.count == 1000
    assert len(r.connections) == 1
    assert r.connections[0].plasticity == "STDP"
    print("  [ok] test_region")


def test_data():
    source = """
data TrainingData {
    source: "dataset.bin"
    shape: [28, 28]
}
"""
    prog = parse_source(source)
    assert len(prog.declarations) == 1
    d = prog.declarations[0]
    assert isinstance(d, DataDef)
    assert d.name == "TrainingData"
    assert d.source == "dataset.bin"
    assert d.shape == [28, 28]
    print("  [ok] test_data")


def test_train_infer():
    source = """
train Cortex on ChatData {
    epochs: 100
    rule: hebbian
}

infer Cortex on input {
    output -> result
}
"""
    prog = parse_source(source)
    assert len(prog.declarations) == 2
    assert isinstance(prog.declarations[0], TrainStmt)
    assert isinstance(prog.declarations[1], InferStmt)
    assert prog.declarations[0].region == "Cortex"
    assert prog.declarations[1].output == "result"
    print("  [ok] test_train_infer")


def test_full_program():
    source = open("examples/chat_neuron.million").read()
    prog = parse_source(source)
    assert len(prog.declarations) == 5
    names = [type(d).__name__ for d in prog.declarations]
    assert "NeuronDef" in names
    assert "RegionDef" in names
    assert "DataDef" in names
    assert "TrainStmt" in names
    assert "InferStmt" in names
    print("  [ok] test_full_program")


if __name__ == "__main__":
    print("Running parser tests...")
    test_empty()
    test_neuron_minimal()
    test_region()
    test_data()
    test_train_infer()
    test_full_program()
    print("All parser tests passed!")
