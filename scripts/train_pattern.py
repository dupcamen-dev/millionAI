#!/usr/bin/env python3
"""End-to-end training script for Pattern Classifier."""
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compiler.compile import compile_million, PROJECT_ROOT


def find_c_compiler():
    candidates = ["gcc", "clang", "cl"]
    for cc in candidates:
        try:
            subprocess.run([cc, "--version"], capture_output=True, check=True)
            return cc
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run([cc, "/?"], capture_output=True, check=True)
                return cc
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
    return None


def compile_c(source_c: Path, binary: Path, cc: str) -> bool:
    try:
        if cc == "cl":
            subprocess.run(
                [cc, str(source_c), "/Fe" + str(binary), "/link", "msvcrt.lib"],
                check=True, capture_output=True, text=True,
            )
        else:
            subprocess.run(
                [cc, "-o", str(binary), str(source_c), "-lm", "-O2"],
                check=True, capture_output=True, text=True,
            )
        return True
    except subprocess.CalledProcessError as e:
        print(f"      Build error: {e.stderr[:200]}")
        return False


def simulate_in_python(ir_module):
    """Simulate pattern classifier behavior in pure Python."""
    import math
    print("\n[Python simulation] Training pattern classifier...")
    n_neurons = 4
    nuc_size = 8
    levels = 4
    lr = 0.001
    stdp_lr = 0.01
    epochs = 5

    # patterns: 4 distinct text lines
    patterns = ["ABCD", "EFGH", "IJKL", "MNOP"]

    def encode(text, size):
        vec = [0.0] * size
        for i in range(min(len(text), size)):
            vec[i] = ord(text[i]) / 128.0 - 0.5
        return vec

    def unfold(nuc, level):
        n = len(nuc)
        out = [0.0] * (n * levels)
        for i in range(len(out)):
            s = 0.0
            for j in range(n):
                s += nuc[j] * math.sin(i * j + level)
            out[i] = math.tanh(s / n)
        return out

    def compress(arr):
        n_out = len(arr) // levels
        out = [0.0] * n_out
        group = max(1, len(arr) // n_out)
        for i in range(n_out):
            s = 0.0
            start = i * group
            for j in range(min(group, len(arr) - start)):
                s += arr[start + j]
            out[i] = math.tanh(s / group)
        return out

    neurons = [[0.0] * nuc_size for _ in range(n_neurons)]
    outputs = [0.0] * n_neurons

    for epoch in range(epochs):
        correct = 0
        for label, text in enumerate(patterns):
            inp = encode(text, nuc_size)
            for ni in range(n_neurons):
                h1 = unfold(neurons[ni], 1)
                h2 = unfold(h1, 2)
                feat = compress(h2)
                out = compress(feat)
                neurons[ni] = [neurons[ni][j] + lr * inp[j] * out[0] for j in range(nuc_size)]
                outputs[ni] = out[0]
            predicted = outputs.index(max(outputs))
            if predicted == label:
                correct += 1
        acc = correct / len(patterns) * 100
        bar = "#" * int(acc / 5) + "." * (20 - int(acc / 5))
        print(f"  Epoch {epoch+1:2d}/{epochs}: [{bar}] {acc:5.1f}%")
    print("  [ok] Simulation complete")


def main():
    source = ROOT / "examples" / "pattern_classifier.million"
    build_dir = ROOT / "build"
    output_c = build_dir / "pattern_classifier.c"

    build_dir.mkdir(parents=True, exist_ok=True)

    print("Million Pattern Classifier v1.0")
    print("=" * 50)
    print(f"  Source: {source.name}")

    # Step 1: Compile Million -> C
    print("\n[1/3] Million -> C ...")
    c_code = compile_million(
        source,
        output_c,
        search_paths=[PROJECT_ROOT, PROJECT_ROOT / "stdlib"],
        backend="c",
    )
    output_c.write_text(c_code, encoding="utf-8")
    print(f"      Generated {len(c_code)} bytes -> {output_c.name}")

    # Step 2: Try to build
    print("\n[2/3] C -> executable ...")
    cc = find_c_compiler()
    if cc:
        binary = build_dir / "pattern_classifier.exe"
        if compile_c(output_c, binary, cc):
            print(f"      Built {binary.name} with {cc}")

            # Step 3: Run native
            print("\n[3/3] Running native binary ...")
            subprocess.run([str(binary)], check=True)
            print("      Done!")
        else:
            print("      Falling back to Python simulation")
            from compiler.ir.million_ir import IRBuilder
            from compiler.compile import parse_program
            mir = IRBuilder().build(parse_program(source))
            simulate_in_python(mir)
    else:
        print("      No C compiler found (install gcc/clang for native)")
        print("      Running pure Python simulation instead")
        from compiler.ir.million_ir import IRBuilder
        from compiler.compile import parse_program
        mir = IRBuilder().build(parse_program(source))
        simulate_in_python(mir)

    print("\nAll done!")


if __name__ == "__main__":
    main()
