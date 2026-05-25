#!/usr/bin/env python3
"""Load pre-trained LM into Million runtime and run inference."""
import sys, json, math, subprocess, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compiler.compile import compile_million, PROJECT_ROOT


def load_weights():
    path = ROOT / "build" / "lm_weights.json"
    with open(path) as f:
        return json.load(f)


def lm_generate_python(seed="h", length=100, temp=0.6):
    """Pure Python inference using exported weights."""
    weights = load_weights()
    vocab = weights["vocab"]
    vocab_size = len(vocab)
    embed_dim = weights["embed_dim"]
    hidden_dim = weights["hidden_dim"]
    w_ih = __import__("numpy").array(weights["w_ih"])
    w_hh = __import__("numpy").array(weights["w_hh"])
    b_h = __import__("numpy").array(weights["b_h"])
    w_ho = __import__("numpy").array(weights["w_ho"])
    b_o = __import__("numpy").array(weights["b_o"])
    embedding = __import__("numpy").array(weights["embedding"])
    np = __import__("numpy")

    def char_to_id(c):
        return vocab.index(c) if c in vocab else 0

    def id_to_char(i):
        return vocab[i % vocab_size]

    hidden = np.zeros(hidden_dim)
    result = list(seed)
    for pos in range(length):
        idx = char_to_id(result[-1]) if result else 0
        emb = embedding[idx]
        hidden = np.tanh(emb @ w_ih + hidden @ w_hh + b_h)
        logits = hidden @ w_ho + b_o
        probs = np.exp(logits / temp - np.max(logits) / temp)
        probs /= np.sum(probs)
        next_idx = np.random.choice(vocab_size, p=probs)
        result.append(id_to_char(next_idx))
    return "".join(result)


def generate_c_source():
    """Create a C program that loads LM weights and runs inference."""
    weights = load_weights()
    vocab = weights["vocab"]
    V = len(vocab)
    D = weights["embed_dim"]
    H = weights["hidden_dim"]

    lines = [
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <string.h>",
        "#include <math.h>",
        "#include <time.h>",
        "",
        '#include "../build/lm_weights.h"',
        "",
        f"static const char VOCAB[{V}] = {{",
        "    " + ", ".join(
            "'\\n'" if c == "\n" else "'\\''" if c == "'" else "'\\" + c + "'" if c == "\\" else f"'{c}'"
            for c in vocab
        ),
        "};",
        "",
        "int char_to_id(char c) {",
        "    for (int i = 0; i < LM_VOCAB_SIZE; i++)",
        "        if (VOCAB[i] == c) return i;",
        "    return 0;",
        "}",
        "",
        "char id_to_char(int i) { return VOCAB[i % LM_VOCAB_SIZE]; }",
        "",
        "void lm_step(int input_id, float* hidden, float* logits_out) {",
        "    float emb[LM_EMBED_DIM];",
        f"    for (int i = 0; i < LM_EMBED_DIM; i++)",
        f"        emb[i] = lm_embedding[input_id * LM_EMBED_DIM + i];",
        "    float new_h[LM_HIDDEN_DIM];",
        "    for (int i = 0; i < LM_HIDDEN_DIM; i++) {",
        "        float s = lm_b_h[i];",
        "        for (int j = 0; j < LM_EMBED_DIM; j++)",
        f"            s += emb[j] * lm_w_ih[j * LM_HIDDEN_DIM + i];",
        "        for (int j = 0; j < LM_HIDDEN_DIM; j++)",
        f"            s += hidden[j] * lm_w_hh[j * LM_HIDDEN_DIM + i];",
        "        new_h[i] = tanhf(s);",
        "    }",
        "    memcpy(hidden, new_h, sizeof(new_h));",
        "    for (int i = 0; i < LM_VOCAB_SIZE; i++) {",
        "        logits_out[i] = lm_b_o[i];",
        "        for (int j = 0; j < LM_HIDDEN_DIM; j++)",
        f"            logits_out[i] += hidden[j] * lm_w_ho[j * LM_VOCAB_SIZE + i];",
        "    }",
        "}",
        "",
        "int sample(float* logits, float temp) {",
        "    float max_l = logits[0];",
        "    for (int i = 1; i < LM_VOCAB_SIZE; i++)",
        "        if (logits[i] > max_l) max_l = logits[i];",
        "    float sum = 0.0f;",
        "    float probs[LM_VOCAB_SIZE];",
        "    for (int i = 0; i < LM_VOCAB_SIZE; i++) {",
        "        probs[i] = expf((logits[i] - max_l) / temp);",
        "        sum += probs[i];",
        "    }",
        "    float r = (float)rand() / RAND_MAX;",
        "    float cum = 0.0f;",
        "    for (int i = 0; i < LM_VOCAB_SIZE; i++) {",
        "        cum += probs[i] / sum;",
        "        if (r < cum) return i;",
        "    }",
        "    return LM_VOCAB_SIZE - 1;",
        "}",
        "",
        "int main(int argc, char** argv) {",
        "    srand((unsigned int)time(NULL));",
        '    const char* seed = argc > 1 ? argv[1] : "h";',
        "    int length = argc > 2 ? atoi(argv[2]) : 100;",
        "    float temp = argc > 3 ? atof(argv[3]) : 0.6f;",
        "",
        "    float hidden[LM_HIDDEN_DIM];",
        "    memset(hidden, 0, sizeof(hidden));",
        "    float logits[LM_VOCAB_SIZE];",
        "",
        '    printf("Seed: %s\\n", seed);',
        '    printf("Generate: ");',
        "    printf(\"%s\", seed);",
        "    int last_id = char_to_id(seed[strlen(seed) - 1]);",
        "    for (int i = 0; i < length; i++) {",
        "        lm_step(last_id, hidden, logits);",
        "        int next = sample(logits, temp);",
        "        printf(\"%c\", id_to_char(next));",
        "        last_id = next;",
        "    }",
        '    printf("\\n");',
        "    return 0;",
        "}",
    ]
    return "\n".join(lines)


def main():
    build_dir = ROOT / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    print("Million Language Model Inference")
    print("=" * 50)

    # Step 1: Generate C source
    print("\n[1/4] Generating C inference source...")
    c_source = generate_c_source()
    c_path = build_dir / "lm_inference.c"
    c_path.write_text(c_source, encoding="utf-8")
    print(f"      Written: {c_path.name}")

    # Step 2: Find C compiler
    print("\n[2/4] Compiling C -> executable...")
    cc = "gcc"
    try:
        subprocess.run([cc, "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            subprocess.run(["clang", "--version"], capture_output=True, check=True)
            cc = "clang"
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("      No C compiler found.")
            print("\n[3/4] Running Python inference instead:")
            print("=" * 50)
            for seed in ["h", "m", "n", "b"]:
                gen = lm_generate_python(seed=seed, length=80, temp=0.6)
                print(f"  '{seed}' -> {gen}")
            print("Done!")
            return

    binary = build_dir / "lm_inference.exe"
    result = subprocess.run(
        [cc, "-o", str(binary), str(c_path), "-lm", "-O2"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"      Build error: {result.stderr[:200]}")
        print("      Falling back to Python inference...")
        for seed in ["h", "m", "n", "b"]:
            gen = lm_generate_python(seed=seed, length=80, temp=0.6)
            print(f"  '{seed}' -> {gen}")
        return

    print(f"      Built: {binary.name}")

    # Step 3: Run native inference
    print("\n[3/4] Native inference results:")
    print("=" * 50)
    for seed in ["h", "m", "n", "b"]:
        p = subprocess.Popen(
            [str(binary), seed, "80", "0.6"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        out, _ = p.communicate(timeout=10)
        for line in out.strip().split("\n"):
            if line.startswith("Generate:"):
                print(f"  {line}")

    # Step 4: Million compilation + integration
    print("\n[4/4] Million integration demo...")
    source = ROOT / "examples" / "language_model.million"
    if source.exists():
        try:
            c_code = compile_million(source, backend="c")
            print(f"      Compiled language_model.million -> {len(c_code)} bytes")

            # Create integrated C program: LM + Million
            integrated_c = ROOT / "build" / "lm_million_integrated.c"
            million_lines = c_code.split("\n")

            # Find where main() starts in Million code, inject LM weights before it
            main_idx = -1
            for i, line in enumerate(million_lines):
                if "int main(void)" in line:
                    main_idx = i
                    break

            if main_idx > 0:
                inject = [
                    '#include "../build/lm_weights.h"',
                    "",
                    "/* LM inference functions injected by run_lm.py */",
                    "static const char LM_VOCAB[] = {",
                    "    " + ", ".join(
                        "'\\n'" if c == "\n" else "'\\''" if c == "'" else "'\\" + c + "'" if c == "\\" else f"'{c}'"
                        for c in "abcdefghijklmnopqrstuvwxyz \n.,!?'\";:-"
                    ),
                    "};",
                    "#define LM_VOCAB_SIZE 42",
                    "",
                    "int lm_char_to_id(char c) {",
                    "    for (int i = 0; i < LM_VOCAB_SIZE; i++)",
                    "        if (LM_VOCAB[i] == c) return i;",
                    "    return 0;",
                    "}",
                    "",
                    "void lm_infer(float* hidden, int input_id, float* output_probs) {",
                    "    float emb[LM_EMBED_DIM];",
                    "    for (int i = 0; i < LM_EMBED_DIM; i++)",
                    "        emb[i] = lm_embedding[input_id * LM_EMBED_DIM + i];",
                    "    float new_h[LM_HIDDEN_DIM];",
                    "    for (int i = 0; i < LM_HIDDEN_DIM; i++) {",
                    "        float s = lm_b_h[i];",
                    "        for (int j = 0; j < LM_EMBED_DIM; j++)",
                    "            s += emb[j] * lm_w_ih[j * LM_HIDDEN_DIM + i];",
                    "        for (int j = 0; j < LM_HIDDEN_DIM; j++)",
                    "            s += hidden[j] * lm_w_hh[j * LM_HIDDEN_DIM + i];",
                    "        new_h[i] = tanhf(s);",
                    "    }",
                    "    memcpy(hidden, new_h, sizeof(new_h));",
                    "    float max_l = -1e10f;",
                    "    for (int i = 0; i < LM_VOCAB_SIZE; i++) {",
                    "        output_probs[i] = lm_b_o[i];",
                    "        for (int j = 0; j < LM_HIDDEN_DIM; j++)",
                    "            output_probs[i] += hidden[j] * lm_w_ho[j * LM_VOCAB_SIZE + i];",
                    "        if (output_probs[i] > max_l) max_l = output_probs[i];",
                    "    }",
                    "    float sum = 0.0f;",
                    "    for (int i = 0; i < LM_VOCAB_SIZE; i++) {",
                    "        output_probs[i] = expf(output_probs[i] - max_l);",
                    "        sum += output_probs[i];",
                    "    }",
                    "    for (int i = 0; i < LM_VOCAB_SIZE; i++)",
                    "        output_probs[i] /= sum;",
                    "}",
                    "",
                ]

                # Insert after includes, before main
                million_lines[main_idx:main_idx] = inject
                integrated_c.write_text("\n".join(million_lines), encoding="utf-8")
                print(f"      Created integrated LM+Million: {integrated_c.name}")

                # Try to compile integrated version
                integrated_bin = ROOT / "build" / "lm_million.exe"
                result2 = subprocess.run(
                    [cc, "-o", str(integrated_bin), str(integrated_c), "-lm", "-O2"],
                    capture_output=True, text=True, timeout=15,
                )
                if result2.returncode == 0:
                    print(f"      Built integrated binary: {integrated_bin.name}")
                    print("\n      Running LM+Million demo...")
                    p = subprocess.Popen(
                        [str(integrated_bin)],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True,
                    )
                    out, _ = p.communicate(input="\n", timeout=5)
                    for line in out.strip().split("\n"):
                        print(f"      {line}")
                else:
                    print(f"      Build note: {result2.stderr[:100]}")
        except Exception as e:
            print(f"      Note: {e}")
    else:
        print(f"      Skip: {source.name} not yet created")

    print("\nAll done!")


if __name__ == "__main__":
    main()
