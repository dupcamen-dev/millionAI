#!/usr/bin/env python3
"""Train a tiny character-level language model and export weights for Million."""
import sys, os, json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --- Character vocabulary ---
CHARS = "abcdefghijklmnopqrstuvwxyz \n.,!?'\";:-"
VOCAB_SIZE = len(CHARS)

def char_to_id(c):
    if c in CHARS:
        return CHARS.index(c)
    return 0

def id_to_char(i):
    return CHARS[i % VOCAB_SIZE]

def encode(text, size=None):
    ids = [char_to_id(c) for c in text.lower() if c in CHARS]
    if size:
        ids = ids[:size]
    return ids

# --- Tiny Recurrent LM ---
class TinyCharLM:
    def __init__(self, embed_dim=16, hidden_dim=32):
        self.embed_dim = embed_dim
        self.hidden_dim = hidden_dim
        self.embedding = np.random.randn(VOCAB_SIZE, embed_dim) * 0.02
        self.w_hh = np.random.randn(hidden_dim, hidden_dim) * 0.02
        self.w_ih = np.random.randn(embed_dim, hidden_dim) * 0.02
        self.b_h = np.zeros(hidden_dim)
        self.w_ho = np.random.randn(hidden_dim, VOCAB_SIZE) * 0.02
        self.b_o = np.zeros(VOCAB_SIZE)

    def forward(self, inputs, hidden=None):
        n = len(inputs)
        if hidden is None:
            hidden = np.zeros(self.hidden_dim)
        outputs = []
        hiddens = [hidden]
        for i in range(n):
            emb = self.embedding[inputs[i]]
            hidden = np.tanh(emb @ self.w_ih + hidden @ self.w_hh + self.b_h)
            logits = hidden @ self.w_ho + self.b_o
            outputs.append(logits)
            hiddens.append(hidden)
        return np.array(outputs), np.array(hiddens[1:])

    def loss_and_grad(self, inputs, targets):
        outputs, hiddens = self.forward(inputs)
        loss = 0.0
        d_embed = np.zeros_like(self.embedding)
        d_w_hh = np.zeros_like(self.w_hh)
        d_w_ih = np.zeros_like(self.w_ih)
        d_b_h = np.zeros_like(self.b_h)
        d_w_ho = np.zeros_like(self.w_ho)
        d_b_o = np.zeros_like(self.b_o)
        d_hidden_next = np.zeros(self.hidden_dim)

        for t in reversed(range(len(inputs))):
            logits = outputs[t]
            probs = np.exp(logits - np.max(logits))
            probs /= np.sum(probs)
            d_logits = probs.copy()
            d_logits[targets[t]] -= 1.0
            loss += -math.log(max(probs[targets[t]], 1e-10))

            d_w_ho += np.outer(hiddens[t], d_logits)
            d_b_o += d_logits

            d_hidden = d_logits @ self.w_ho.T + d_hidden_next
            d_hidden_raw = d_hidden * (1 - hiddens[t] ** 2)

            emb = self.embedding[inputs[t]]
            d_w_ih += np.outer(emb, d_hidden_raw)
            prev_h = hiddens[t - 1] if t > 0 else np.zeros(self.hidden_dim)
            d_w_hh += np.outer(prev_h, d_hidden_raw)
            d_b_h += d_hidden_raw

            d_embed[inputs[t]] += self.w_ih @ d_hidden_raw
            d_hidden_next = self.w_hh.T @ d_hidden_raw

        return loss / len(inputs), {
            "embedding": d_embed,
            "w_hh": d_w_hh, "w_ih": d_w_ih, "b_h": d_b_h,
            "w_ho": d_w_ho, "b_o": d_b_o,
        }

    def train(self, texts, epochs=100, lr=0.01):
        all_ids = [encode(t) for t in texts]
        for epoch in range(epochs):
            total_loss = 0.0
            total_chars = 0
            for ids in all_ids:
                if len(ids) < 2:
                    continue
                inputs = ids[:-1]
                targets = ids[1:]
                loss, grads = self.loss_and_grad(inputs, targets)
                total_loss += loss * len(inputs)
                total_chars += len(inputs)
                self.embedding -= lr * grads["embedding"]
                self.w_hh -= lr * grads["w_hh"]
                self.w_ih -= lr * grads["w_ih"]
                self.b_h -= lr * grads["b_h"]
                self.w_ho -= lr * grads["w_ho"]
                self.b_o -= lr * grads["b_o"]
            avg_loss = total_loss / max(total_chars, 1)
            if epoch % 20 == 0 or epoch == epochs - 1:
                bar = "#" * int((1 - avg_loss / 4) * 20) + "." * min(20, int(avg_loss / 4 * 20))
                print(f"  Epoch {epoch:3d}: loss={avg_loss:.4f} [{bar}]")

    def generate(self, seed="h", length=50, temp=0.8):
        hidden = np.zeros(self.hidden_dim)
        ids = encode(seed)
        result = list(seed)
        for i in range(length):
            if ids:
                emb = self.embedding[ids[-1]]
            else:
                emb = np.zeros(self.embed_dim)
            hidden = np.tanh(emb @ self.w_ih + hidden @ self.w_hh + self.b_h)
            logits = hidden @ self.w_ho + self.b_o
            probs = np.exp(logits / temp - np.max(logits) / temp)
            probs /= np.sum(probs)
            idx = np.random.choice(VOCAB_SIZE, p=probs)
            result.append(id_to_char(idx))
            ids = [idx]
        return "".join(result)

    def export_weights(self, path):
        """Export weights as a C header for Million runtime."""
        lines = [
            "#ifndef MILLION_LM_WEIGHTS_H",
            "#define MILLION_LM_WEIGHTS_H",
            "",
            f"/* Tiny Char LM weights */",
            f"/* Vocab={VOCAB_SIZE}, embed={self.embed_dim}, hidden={self.hidden_dim} */",
            "",
            f"#define LM_VOCAB_SIZE {VOCAB_SIZE}",
            f"#define LM_EMBED_DIM {self.embed_dim}",
            f"#define LM_HIDDEN_DIM {self.hidden_dim}",
            "",
        ]

        def export_arr(name, arr):
            flat = arr.flatten()
            vals = ", ".join(f"{v:.8f}f" for v in flat)
            lines.append(f"static float {name}[{len(flat)}] = {{ {vals} }};")
            lines.append("")

        export_arr("lm_embedding", self.embedding)
        export_arr("lm_w_hh", self.w_hh)
        export_arr("lm_w_ih", self.w_ih)
        export_arr("lm_b_h", self.b_h)
        export_arr("lm_w_ho", self.w_ho)
        export_arr("lm_b_o", self.b_o)

        lines.append("#endif /* MILLION_LM_WEIGHTS_H */")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        print(f"      Exported weights: {path}")


def main():
    print("Tiny Char Language Model for Million")
    print("=" * 50)

    # Load or create data
    data_path = ROOT / "data" / "lm_data.txt"
    texts = [line.strip() for line in data_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"\n  Training data: {len(texts)} lines")
    for t in texts:
        print(f"    - {t}")

    # Train
    print("\n  Training tiny char LM...")
    model = TinyCharLM(embed_dim=16, hidden_dim=32)
    model.train(texts, epochs=200, lr=0.02)

    # Generate samples
    print("\n  Generated samples:")
    for seed in ["h", "m", "n", "b"]:
        gen = model.generate(seed=seed, length=30, temp=0.6)
        print(f"    '{seed}' -> {gen}")

    # Export
    print("\n  Exporting...")
    weights_dir = ROOT / "build"
    weights_dir.mkdir(parents=True, exist_ok=True)
    model.export_weights(weights_dir / "lm_weights.h")

    # Also export as JSON for Python use
    export = {
        "vocab": list(CHARS),
        "embed_dim": model.embed_dim,
        "hidden_dim": model.hidden_dim,
        "embedding": model.embedding.tolist(),
        "w_hh": model.w_hh.tolist(),
        "w_ih": model.w_ih.tolist(),
        "b_h": model.b_h.tolist(),
        "w_ho": model.w_ho.tolist(),
        "b_o": model.b_o.tolist(),
    }
    json_path = weights_dir / "lm_weights.json"
    json.dump(export, open(json_path, "w"))
    print(f"      Exported: {json_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
