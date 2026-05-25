"""Emit archive gradient and hybrid training C functions."""


class CBackpropEmitter:
    """Generate backprop helpers for archive unfold/compress."""

    def __init__(self, emit_fn):
        self.emit = emit_fn
        self.indent = 0

    def emit_block(self):
        self.emit("/* ========= Archive Gradients ========= */")
        self._emit_unfold_grad()
        self._emit_compress_grad()
        self._emit_hybrid_training()

    def _emit_unfold_grad(self):
        self.emit(
            "void archive_unfold_grad(float* in, int in_size, float* out, int out_size,"
        )
        self.emit("    int level, float* grad_out, float* grad_in) {")
        self.indent = 1
        self.emit("for (int j = 0; j < in_size; j++) grad_in[j] = 0.0f;")
        self.emit("for (int i = 0; i < out_size; i++) {")
        self.indent += 1
        self.emit("float sum = 0.0f;")
        self.emit("for (int j = 0; j < in_size; j++) {")
        self.indent += 1
        self.emit("sum += in[j] * sinf((float)(i * j + level));")
        self.indent -= 1
        self.emit("}")
        self.emit("float act = tanhf(sum / (float)in_size);")
        self.emit("float dtanh = 1.0f - act * act;")
        self.emit("for (int j = 0; j < in_size; j++) {")
        self.indent += 1
        self.emit(
            "grad_in[j] += grad_out[i] * dtanh * sinf((float)(i * j + level)) /"
            " (float)in_size;"
        )
        self.indent -= 1
        self.emit("}")
        self.indent -= 1
        self.emit("}")
        self.indent = 0
        self.emit()

    def _emit_compress_grad(self):
        self.emit(
            "void archive_compress_grad(float* in, int in_size, float* out, int out_size,"
        )
        self.emit("    float* grad_out, float* grad_in) {")
        self.indent = 1
        self.emit("int group = in_size / out_size;")
        self.emit("if (group < 1) group = 1;")
        self.emit("for (int j = 0; j < in_size; j++) grad_in[j] = 0.0f;")
        self.emit("for (int i = 0; i < out_size; i++) {")
        self.indent += 1
        self.emit("float sum = 0.0f;")
        self.emit("int start = i * group;")
        self.emit("for (int j = 0; j < group && (start + j) < in_size; j++) {")
        self.indent += 1
        self.emit("sum += in[start + j];")
        self.indent -= 1
        self.emit("}")
        self.emit("float act = tanhf(sum / (float)group);")
        self.emit("float dtanh = 1.0f - act * act;")
        self.emit("for (int j = 0; j < group && (start + j) < in_size; j++) {")
        self.indent += 1
        self.emit("grad_in[start + j] += grad_out[i] * dtanh / (float)group;")
        self.indent -= 1
        self.emit("}")
        self.indent -= 1
        self.emit("}")
        self.indent = 0
        self.emit()

    def _emit_hybrid_training(self):
        self.emit("/* Hybrid gradient + STDP training step (template via macros) */")
        self.emit(
            "#define TRAIN_STEP_HYBRID(NT, NS, LR, STDP_LR) do { \\"
        )
        self.emit("    float fwd_out[NS]; \\")
        self.emit("    float grad_out[NS]; \\")
        self.emit("    float grad_nuc[NS]; \\")
        self.emit("    archive_unfold(n->nucleus, NS, fwd_out, NS * 3, 1); \\")
        self.emit("    float loss = fwd_out[0] - target; \\")
        self.emit("    for (int gi = 0; gi < NS; gi++) grad_out[gi] = 2.0f * loss; \\")
        self.emit("    archive_unfold_grad(n->nucleus, NS, fwd_out, NS * 3, 1, grad_out, grad_nuc); \\")
        self.emit("    for (int gi = 0; gi < NS; gi++) n->nucleus[gi] -= (LR) * grad_nuc[gi]; \\")
        self.emit("    apply_stdp(n->nucleus, NS, input, NS, n->output, (STDP_LR)); \\")
        self.emit("} while(0)")
        self.emit()
