#!/usr/bin/env python3
"""Tests for C code generation quality."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, PROJECT_ROOT


def test_train_loads_dataset():
    c = compile_million(PROJECT_ROOT / "examples" / "chat_neuron.million", backend="c")
    assert "load_ChatData" in c
    assert "apply_hebbian" in c
    assert "train_Cortex" in c
    print("  [ok] test_train_loads_dataset")


def test_connections():
    c = compile_million(PROJECT_ROOT / "examples" / "chat_neuron.million", backend="c")
    assert "Cortex_syn_data" in c
    assert "Cortex_syn_offsets" in c
    assert "apply_stdp" in c
    print("  [ok] test_connections")


def test_minimal_example():
    c = compile_million(PROJECT_ROOT / "examples" / "minimal.million", backend="c")
    assert "process_Echo" in c
    assert "infer_Pool" in c
    assert "int main" in c
    print("  [ok] test_minimal_example")


if __name__ == "__main__":
    print("Running codegen tests...")
    test_train_loads_dataset()
    test_connections()
    test_minimal_example()
    print("All codegen tests passed!")
