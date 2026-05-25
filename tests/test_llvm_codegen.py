#!/usr/bin/env python3
"""Tests for LLVM IR codegen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, llvmlite_available, PROJECT_ROOT


def test_llvm_module_verifies():
    if not llvmlite_available():
        print("  [skip] test_llvm_module_verifies (llvmlite not installed)")
        return
    ir_code = compile_million(
        PROJECT_ROOT / "examples" / "minimal.million", backend="llvm"
    )
    assert '@"main"' in ir_code or "define i32 @main" in ir_code
    assert "process_Echo" in ir_code
    assert "archive_unfold" in ir_code
    assert "archive_compress" in ir_code
    assert "archive_unfold_grad" in ir_code
    assert "archive_compress_grad" in ir_code
    assert "sinf" in ir_code
    print("  [ok] test_llvm_module_verifies")


def test_llvm_grad_functions_verify():
    if not llvmlite_available():
        print("  [skip] test_llvm_grad_functions_verify (llvmlite not installed)")
        return
    ir_code = compile_million(
        PROJECT_ROOT / "examples" / "spiking_chat.million", backend="llvm"
    )
    assert "archive_unfold_grad" in ir_code
    assert "archive_compress_grad" in ir_code
    assert "define void" in ir_code
    print("  [ok] test_llvm_grad_functions_verify")


def test_llvm_fallback_to_c():
    c = compile_million(PROJECT_ROOT / "examples" / "minimal.million", backend="c")
    assert "int process_Echo" in c
    print("  [ok] test_llvm_fallback_to_c")


def test_auto_backend():
    code = compile_million(PROJECT_ROOT / "examples" / "minimal.million", backend="auto")
    assert len(code) > 100
    print("  [ok] test_auto_backend")


if __name__ == "__main__":
    print("Running LLVM codegen tests...")
    test_llvm_module_verifies()
    test_llvm_grad_functions_verify()
    test_llvm_fallback_to_c()
    test_auto_backend()
    print("All LLVM tests passed!")
