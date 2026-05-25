#!/usr/bin/env python3
"""Generate Qwen-Million runtime: loads compressed weights into neurons."""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_H = ROOT / "build" / "qwen_million" / "qwen_weights.h"
OUTPUT_C = ROOT / "build" / "qwen_million" / "qwen_runtime.c"

def generate_runtime():
    """Generate C file that initializes nuclei with Qwen weights."""
    if not WEIGHTS_H.exists():
        print("Run convert_qwen_to_million.py first")
        return

    # Parse the weights header to extract nucleus data
    with open(WEIGHTS_H, "r") as f:
        content = f.read()

    nuclei = []
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("static float qwen_nucleus_"):
            # Parse nucleus definition
            name = line.split("qwen_nucleus_")[1].split("[")[0]
            size_match = line.split("[")[1].split("]")[0]
            size = int(size_match)

            # Read comment before for weight_name
            comment = lines[i - 1] if i > 0 else ""

            # Read array values
            i += 1
            values = []
            while i < len(lines) and "};" not in lines[i]:
                val_line = lines[i].strip().rstrip(",")
                for v in val_line.split(","):
                    v = v.strip()
                    if v and v.endswith("f"):
                        values.append(float(v.rstrip("f")))
                i += 1

            if values:
                nuclei.append({
                    "idx": int(name),
                    "size": size,
                    "values": values,
                    "comment": comment,
                })
        i += 1

    print(f"Parsed {len(nuclei)} nuclei from {WEIGHTS_H.name}")

    # Generate runtime C file
    with open(OUTPUT_C, "w") as f:
        f.write("/* Qwen-Million Runtime: loads compressed weights into neurons */\n")
        f.write("/* Auto-generated */\n\n")
        f.write('#include "qwen_weights.h"\n')
        f.write('#include "models/qwen_million.c"\n\n')
        f.write("static void load_qwen_weights(void) {\n")

        for nuc in nuclei[:5]:  # Show first 5 as example
            name = f"qwen_nucleus_{nuc['idx']}"
            vals = ", ".join(f"{v:.6f}f" for v in nuc["values"][:8])
            f.write(f"    // {nuc['comment'].strip()}\n")
            f.write(f"    memcpy(embed_neurons[0].nucleus, {name}, sizeof({name}));\n")
            f.write(f"    // Values: {vals}...\n\n")

        f.write("    // TODO: map each qwen_nucleus_N to the correct neuron\n")
        f.write("}\n\n")
        f.write("int main(int argc, char** argv) {\n")
        f.write("    load_qwen_weights();\n")
        f.write("    init_all();\n")
        f.write('    printf("Qwen-Million ready.\\n");\n')
        f.write("    return 0;\n")
        f.write("}\n")

    print(f"Generated {OUTPUT_C.name} ({OUTPUT_C.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_runtime()
