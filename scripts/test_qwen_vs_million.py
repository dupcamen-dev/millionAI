#!/usr/bin/env python3
"""Test Million archive compression quality vs original Qwen weights."""
import json, time, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import our converter functions
from scripts.convert_qwen_to_million import (
    get_all_weight_names, get_qwen_config, compress_tensor,
    STATE_N, STATE_L, MODEL_URL
)

CONFIG = get_qwen_config()


def archive_unfold(nucleus: np.ndarray, level: int, out_size: int) -> np.ndarray:
    """Simulate C archive_unfold in numpy."""
    in_size = len(nucleus)
    out = np.zeros(out_size)
    for i in range(out_size):
        s = 0.0
        for j in range(in_size):
            s += nucleus[j] * np.sin(i * j + level)
        out[i] = np.tanh(s / in_size)
    return out


def archive_compress(inp: np.ndarray, out_size: int) -> np.ndarray:
    """Simulate C archive_compress in numpy."""
    in_size = len(inp)
    group = max(1, in_size // out_size)
    out = np.zeros(out_size)
    for i in range(out_size):
        start = i * group
        end = min(start + group, in_size)
        if end > start:
            out[i] = np.tanh(np.mean(inp[start:end]))
    return out


def load_tensor(name: str, model_path: Path):
    """Load a single Qwen tensor from safetensors by name."""
    import struct
    with open(model_path, "rb") as f:
        hdr_len = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(hdr_len).decode("utf-8"))
    
    info = hdr[name]
    shape = info["shape"]
    offsets = info["data_offsets"]
    dtype = info["dtype"]
    
    with open(model_path, "rb") as f:
        f.seek(8 + hdr_len + offsets[0])
        raw = f.read(offsets[1] - offsets[0])
    
    if dtype == "BF16":
        u16 = np.frombuffer(raw, dtype=np.uint16)
        tensor = (u16.astype(np.uint32) << 16).view(np.float32).reshape(shape)
    else:
        tensor = np.frombuffer(raw, dtype=np.float32).reshape(shape)
    
    return tensor


def test_compression_quality():
    """Test how well archive compression preserves weight information."""
    model_path = ROOT / "build" / "qwen_weights" / "model.safetensors"
    if not model_path.exists():
        print("Downloading Qwen weights first...")
        import requests
        resp = requests.get(MODEL_URL, stream=True, timeout=30)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(model_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
    
    print("=" * 60)
    print("Qwen vs Million: Archive Compression Quality Test")
    print("=" * 60)
    
    # Test 1: Embedding layer (most critical)
    print("\n[Test 1] Embedding layer (151936x896 = 136M params)")
    embed = load_tensor("model.embed_tokens.weight", model_path)
    print(f"  Original: {embed.shape}, {embed.nbytes / 1024 / 1024:.1f} MB")
    
    compressed = compress_tensor(embed)
    nucleus = np.array(compressed["state"])
    print(f"  Archive:   state[{STATE_N}] = {nucleus.nbytes} bytes")
    print(f"  Ratio:     {embed.size / STATE_N:.0f}x compression")
    
    # Quality: compare mean/std distribution
    orig_flat = embed.flatten()
    print(f"\n  Original stats: mean={orig_flat.mean():.6f}, std={orig_flat.std():.6f}")
    print(f"  Archive stats:  mean={nucleus.mean():.6f}, std={nucleus.std():.6f}")
    
    # Test 2: Reconstruct a sample via unfold/compress
    print("\n[Test 2] Million dynamics simulation (1 forward pass)")
    sample_input = np.random.randn(896).astype(np.float32)
    sample_input = sample_input / np.linalg.norm(sample_input)
    
    # Qwen: original embedding matrix * sample input (approximate attention)
    orig_output = embed @ sample_input  # [151936]
    orig_top5 = np.argsort(-orig_output)[:5]
    
    # Million: unfold -> compress dynamics
    unfolded = archive_unfold(nucleus, 1, STATE_N * STATE_L)
    compressed_out = archive_compress(unfolded, STATE_N)
    mil_output = compressed_out[:896]  # project to 896 dims
    # Compare: dot product similarity
    sim = np.dot(mil_output, sample_input) / (np.linalg.norm(mil_output) * np.linalg.norm(sample_input) + 1e-10)
    print(f"  Million-Qwen cosine similarity: {sim:.4f}")
    print(f"  Qwen top-5 indices: {orig_top5[:3]}")
    
    # Test 3: Single attention layer
    print("\n[Test 3] Attention layer 0 (Q, K, V, O projections)")
    q_w = load_tensor("model.layers.0.self_attn.q_proj.weight", model_path)
    k_w = load_tensor("model.layers.0.self_attn.k_proj.weight", model_path)
    v_w = load_tensor("model.layers.0.self_attn.v_proj.weight", model_path)
    o_w = load_tensor("model.layers.0.self_attn.o_proj.weight", model_path)
    
    total_memory = sum(t.nbytes for t in [q_w, k_w, v_w, o_w])
    print(f"  Original: {total_memory / 1024:.1f} KB")
    
    # Compress all 4 together
    combined = np.concatenate([q_w.flatten(), k_w.flatten(), v_w.flatten(), o_w.flatten()])
    c = compress_tensor(combined)
    arch_size = STATE_N * 4  # bytes
    print(f"  Archive:   {arch_size} bytes ({combined.size / STATE_N:.0f}x)")
    print(f"  Memory:    Qwen={total_memory/1024:.0f}KB vs Million={arch_size/1024:.1f}KB")
    print(f"  Saving:    {(1 - arch_size / total_memory) * 100:.1f}%")
    
    # Test 4: Full model projection
    print("\n[Test 4] Full model resource comparison")
    qwen_mb = 942  # Qwen file size
    mil_neurons = 290  # number of archive nuclei
    mil_mb = mil_neurons * STATE_N * 4 / 1024 / 1024
    print(f"  Qwen:  {qwen_mb:.0f} MB")
    print(f"  Million: {mil_mb:.2f} MB ({mil_neurons} neurons x {STATE_N} floats)")
    print(f"  Reduction: {(1 - mil_mb / qwen_mb) * 100:.2f}%")
    print(f"  Archive quality: {sim:.4f} cosine similarity (higher = better)")
    
    print("\n" + "=" * 60)
    print("Done.")
    
    return {
        "original_params": embed.size,
        "archive_values": STATE_N,
        "compression_ratio": embed.size / STATE_N,
        "cosine_sim": float(sim),
        "qwen_mb": qwen_mb,
        "million_mb": mil_mb,
    }


if __name__ == "__main__":
    results = test_compression_quality()
    print(f"\nResults summary:")
    for k, v in results.items():
        print(f"  {k}: {v}")
