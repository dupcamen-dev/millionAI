#!/usr/bin/env python3
"""Tests for event-driven C codegen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, PROJECT_ROOT
from compiler.ir.million_ir import IRBuilder, MIRSparseConnection
from compiler.ir.sparse_builder import build_sparse_connections
from compiler.compile import parse_program


def test_sparse_connections_built():
    prog = parse_program(PROJECT_ROOT / "examples" / "chat_neuron.million")
    mir = IRBuilder().build(prog)
    region = mir.regions[0]
    assert len(region.sparse_connections) > 0
    assert isinstance(region.sparse_connections[0], MIRSparseConnection)
    print("  [ok] test_sparse_connections_built")


def test_event_queue_in_codegen():
    c = compile_million(PROJECT_ROOT / "examples" / "chat_neuron.million", backend="c")
    assert "SpikeEvent" in c
    assert "event_queue_insert_sorted" in c
    assert "run_region_Cortex" in c
    assert "inject_input" in c
    assert "Synapse" in c
    assert "_syn_offsets" in c
    print("  [ok] test_event_queue_in_codegen")


def test_process_returns_int():
    c = compile_million(PROJECT_ROOT / "examples" / "minimal.million", backend="c")
    assert "int process_Echo" in c
    assert "process_cleanup:" in c
    assert "return fired_Echo" in c
    print("  [ok] test_process_returns_int")


def test_step_region_compat():
    c = compile_million(PROJECT_ROOT / "examples" / "chat_neuron.million", backend="c")
    assert "void step_region_Cortex" in c
    assert "inject_input" in c
    print("  [ok] test_step_region_compat")


def test_spiking_chat_example():
    c = compile_million(PROJECT_ROOT / "examples" / "spiking_chat.million", backend="c")
    assert "run_region_SpikingCortex" in c
    assert "train_step_hybrid_SpikeDNA" in c
    print("  [ok] test_spiking_chat_example")


if __name__ == "__main__":
    print("Running event-driven tests...")
    test_sparse_connections_built()
    test_event_queue_in_codegen()
    test_process_returns_int()
    test_step_region_compat()
    test_spiking_chat_example()
    print("All event-driven tests passed!")
