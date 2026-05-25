#!/usr/bin/env python3
"""Tests for use/import resolution."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import parse_program, compile_million, PROJECT_ROOT


def test_use_stdlib():
    probe = PROJECT_ROOT / "examples" / "_import_probe.million"
    probe.write_text('use "stdlib/neuron_base.million"\n', encoding="utf-8")
    try:
        prog = parse_program(probe)
        names = [d.name for d in prog.declarations if hasattr(d, "name")]
        assert "LIF" in names
        assert "Sensory" in names
        print("  [ok] test_use_stdlib")
    finally:
        if probe.exists():
            probe.unlink()


def test_compile_with_import():
    src = PROJECT_ROOT / "examples" / "with_import.million"
    src.write_text(
        'use "stdlib/neuron_base.million"\n'
        "region R { neurons: LIF[2] }\n"
        "infer R on input { output -> out }\n",
        encoding="utf-8",
    )
    try:
        c = compile_million(src, backend="c")
        assert "process_LIF" in c
        assert "infer_R" in c
        print("  [ok] test_compile_with_import")
    finally:
        if src.exists():
            src.unlink()


if __name__ == "__main__":
    print("Running import tests...")
    test_use_stdlib()
    test_compile_with_import()
    print("All import tests passed!")
