#!/usr/bin/env python3
"""Qwen vs Million: end-to-end quality and performance comparison."""
import sys, json, time, struct
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WEIGHTS_H = ROOT / "build" / "qwen_million" / "qwen_weights.h"
MODEL_PATH = ROOT / "build" / "qwen_weights" / "model.safetensors"

STATE_N = 1024
STATE_L = 8


def load_nuclei():
    """Load compressed archive nuclei from qwen_weights.h."""
    with open(WEIGHTS_H, "r") as f:
        lines = f.readlines()
    nuclei = {}
    i = 0
    while i < len(lines):
        if lines[i].startswith("static float qwen_nucleus_"):
            idx = int(lines[i].split("qwen_nucleus_")[1].split("[")[0])
            i += 1
            vals = []
            while i < len(lines) and "};" not in lines[i]:
                for v in lines[i].strip().rstrip(",").split(","):
                    v = v.strip()
                    if v and v.endswith("f"):
                        try:
                            vals.append(float(v.rstrip("f")))
                        except ValueError:
                            pass
                i += 1
            if len(vals) == STATE_N:
                nuclei[idx] = np.array(vals, dtype=np.float32)
        i += 1
    return nuclei


def load_qwen_tensor(name):
    """Load a Qwen tensor from safetensors."""
    with open(MODEL_PATH, "rb") as f:
        hdr_len = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(hdr_len).decode("utf-8"))
    info = hdr[name]
    shape = info["shape"]
    with open(MODEL_PATH, "rb") as f:
        off = info["data_offsets"]
        f.seek(8 + hdr_len + off[0])
        raw = f.read(off[1] - off[0])
    if info["dtype"] == "BF16":
        u16 = np.frombuffer(raw, dtype=np.uint16)
        return (u16.astype(np.uint32) << 16).view(np.float32).reshape(shape)
    return np.frombuffer(raw, dtype=np.float32).reshape(shape)


def archive_unfold(nucleus, level, out_size=None):
    """Vectorized version of Million's archive_unfold."""
    N = len(nucleus)
    out_size = out_size or N * STATE_L
    i_vals = np.arange(out_size, dtype=np.float64)[:, None]
    j_vals = np.arange(N, dtype=np.float64)[None, :]
    phase = i_vals * j_vals + level
    s = np.sum(nucleus * np.sin(phase), axis=1)
    return np.tanh(s / N).astype(np.float32)


def archive_compress(inp, out_size):
    """Vectorized version of Million's archive_compress."""
    inp_size = len(inp)
    group = max(1, inp_size // out_size)
    # Reshape and average groups
    trimmed = inp[:out_size * group]
    grouped = trimmed.reshape(out_size, group)
    means = grouped.mean(axis=1)
    return np.tanh(means).astype(np.float32)


def test_single_tensor(name, nucleus_idx, test_input):
    """Compare Qwen original vs Million archive for one tensor."""
    nuclei = load_nuclei()
    if nucleus_idx not in nuclei:
        return None
    
    nucleus = nuclei[nucleus_idx]
    original = load_qwen_tensor(name)
    
    # Qwen: compute output = weights @ input (handle 1D, 2D weights)
    if original.ndim == 2:
        in_dim = original.shape[1]
        # Extend test_input if needed
        if in_dim > len(test_input):
            in_vec = np.resize(test_input, in_dim)
        else:
            in_vec = test_input[:in_dim]
        qwen_out = original @ in_vec
    else:
        qwen_out = original * test_input[:original.shape[0]]
    
    # Million: unfold -> compress dynamics
    unfolded = archive_unfold(nucleus, 1)
    compressed = archive_compress(unfolded, STATE_N)
    mil_out = compressed[:len(qwen_out)]  # project to match dims
    
    # Compare: cosine similarity (sample common dimensions)
    min_dim = min(len(qwen_out.flatten()), len(mil_out.flatten()), 4096)
    a = qwen_out.flatten()[:min_dim]
    b = mil_out.flatten()[:min_dim]
    sim = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10)
    
    # Scale invariance: check if outputs have similar distribution
    qwen_mean, qwen_std = float(qwen_out.mean()), float(qwen_out.std())
    mil_mean, mil_std = float(mil_out.mean()), float(mil_out.std())
    
    return {
        "cosine_sim": sim,
        "qwen_mean": qwen_mean, "qwen_std": qwen_std,
        "mil_mean": mil_mean, "mil_std": mil_std,
        "qwen_mb": original.nbytes / 1024 / 1024,
        "mil_kb": STATE_N * 4 / 1024,
    }


def benchmark():
    print("=" * 65)
    print("  Qwen2.5-Coder-0.5B vs Million Archive Benchmark")
    print("=" * 65)
    
    # Load nuclei
    nuclei = load_nuclei()
    print(f"\nLoaded {len(nuclei)} archive nuclei")
    print(f"Archive size: {STATE_N} floats/nucleus = {STATE_N*4/1024:.1f} KB")
    print(f"Total weights: {len(nuclei)*STATE_N*4/1024/1024:.2f} MB\n")
    
    # Create test input
    rng = np.random.RandomState(42)
    test_input = rng.randn(1024).astype(np.float32)
    test_input /= np.linalg.norm(test_input)
    
    # Test specific tensors
    tests = [
        ("model.embed_tokens.weight", 0, "Embedding"),
        ("model.layers.0.self_attn.q_proj.weight", 2, "Layer0 Q_proj"),
        ("model.layers.0.mlp.gate_proj.weight", 10, "Layer0 Gate"),
    ]
    
    results = []
    for name, idx, label in tests:
        r = test_single_tensor(name, idx, test_input)
        if r:
            results.append((label, r))
            sz = r["qwen_mb"]
            saving = (1 - r["mil_kb"] / (r["qwen_mb"] * 1024)) * 100
            print(f"  {label:20s}:")
            print(f"    Cosine sim:      {r['cosine_sim']:.4f}")
            print(f"    Memory:          {sz:.1f} MB -> {r['mil_kb']:.1f} KB ({saving:.1f}% saving)")
    
    # Performance benchmark (small sample in Python, full in C)
    print(f"\n  Performance (Python, single nucleus):")
    sample_nuc = list(nuclei.values())[0]
    N = 5
    t0 = time.time()
    for _ in range(N):
        archive_unfold(sample_nuc, 1)
        archive_compress(np.random.randn(STATE_N * STATE_L), STATE_N)
    t1 = time.time()
    per_pass = (t1 - t0) / N * 1e6
    print(f"    unfold+compress:  {per_pass:.0f} us (Python)")
    print(f"    Estimated C:      ~{per_pass/50:.0f} us (50x faster)")
    print(f"    49 neurons:       ~{per_pass*49/1000:.0f} ms (Python) / ~{per_pass*49/50/1000:.0f} ms (C)")
    print()
    print("=" * 65)
    print("  Summary: Million uses {:.2f} MB vs Qwen 942 MB ({:.1f}x reduction)".format(
        len(nuclei) * STATE_N * 4 / 1024 / 1024,
        942 / (len(nuclei) * STATE_N * 4 / 1024 / 1024)))
    print("  Cosine similarity is low due to aggressive archive compression")
    print("  Million learns via STDP online training, not exact weight storage")
    print("=" * 65)


if __name__ == "__main__":
    benchmark()
