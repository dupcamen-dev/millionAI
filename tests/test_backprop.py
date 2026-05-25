#!/usr/bin/env python3
"""Tests for archive backprop codegen and numerical gradients."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, PROJECT_ROOT


def archive_unfold_forward(inp, level):
    n = len(inp)
    out_size = n * 3
    out = []
    for i in range(out_size):
        s = sum(inp[j] * math.sin(i * j + level) for j in range(n))
        out.append(math.tanh(s / n))
    return out


def archive_unfold_grad_numeric(inp, level, grad_out, eps=1e-4):
    grad_in = [0.0] * len(inp)
    for j in range(len(inp)):
        up = inp[:]
        dn = inp[:]
        up[j] += eps
        dn[j] -= eps
        fu = archive_unfold_forward(up, level)
        fd = archive_unfold_forward(dn, level)
        for i in range(len(grad_out)):
            grad_in[j] += grad_out[i] * (fu[i] - fd[i]) / (2 * eps)
    return grad_in


def archive_unfold_grad_analytic(inp, level, grad_out):
    n = len(inp)
    out_size = n * 3
    grad_in = [0.0] * n
    for i in range(out_size):
        s = sum(inp[j] * math.sin(i * j + level) for j in range(n))
        act = math.tanh(s / n)
        dtanh = 1.0 - act * act
        for j in range(n):
            grad_in[j] += grad_out[i] * dtanh * math.sin(i * j + level) / n
    return grad_in


def test_archive_unfold_grad_numerical():
    inp = [0.1, -0.2, 0.3, 0.0]
    level = 1
    fwd = archive_unfold_forward(inp, level)
    grad_out = [1.0 if i == 0 else 0.0 for i in range(len(fwd))]
    num = archive_unfold_grad_numeric(inp, level, grad_out)
    ana = archive_unfold_grad_analytic(inp, level, grad_out)
    for j in range(len(inp)):
        assert abs(num[j] - ana[j]) < 1e-3, (num[j], ana[j])
    print("  [ok] test_archive_unfold_grad_numerical")


def test_backprop_functions_emitted():
    c = compile_million(PROJECT_ROOT / "examples" / "spiking_chat.million", backend="c")
    assert "archive_unfold_grad" in c
    assert "archive_compress_grad" in c
    assert "train_step_hybrid_SpikeDNA" in c
    print("  [ok] test_backprop_functions_emitted")


def test_hybrid_training_emitted():
    c = compile_million(PROJECT_ROOT / "examples" / "spiking_chat.million", backend="c")
    assert "bptt_backward_SpikingCortex" in c
    assert "tanhf(input[i % ns])" in c
    print("  [ok] test_hybrid_training_emitted")


def test_process_cleanup_frees_malloc():
    c = compile_million(PROJECT_ROOT / "examples" / "chat_neuron.million", backend="c")
    assert "process_cleanup:" in c
    assert "goto process_cleanup" in c
    print("  [ok] test_process_cleanup_frees_malloc")


def test_bptt_checkpoints_emitted():
    c = compile_million(PROJECT_ROOT / "examples" / "spiking_chat.million", backend="c")
    assert "SpikingCortex_ckpt" in c
    assert "bptt_backward_SpikingCortex" in c
    print("  [ok] test_bptt_checkpoints_emitted")


if __name__ == "__main__":
    print("Running backprop tests...")
    test_archive_unfold_grad_numerical()
    test_backprop_functions_emitted()
    test_hybrid_training_emitted()
    test_process_cleanup_frees_malloc()
    test_bptt_checkpoints_emitted()
    print("All backprop tests passed!")
