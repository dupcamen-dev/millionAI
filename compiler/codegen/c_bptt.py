"""Emit BPTT checkpoint storage and backward pass for event-driven regions."""


class CBPTTEmitter:
    """Generate nucleus checkpoints per timestep and backward training."""

    def __init__(self, emit_fn, indent_setter):
        self.emit = emit_fn
        self.set_indent = indent_setter

    def emit_region_bptt(
        self,
        region_name: str,
        neuron_type: str,
        count: int,
        nucleus_size: int,
        steps: int,
    ):
        upper = region_name.upper()
        self.emit(f"/* BPTT checkpoints: {region_name} */")
        self.emit(f"#define BPTT_STEPS_{upper} {steps}")
        self.emit(
            f"static float {region_name}_ckpt[{count}][{steps}][{nucleus_size}];"
        )
        self.emit()
        self.emit(
            f"void bptt_backward_{region_name}(float* input, int input_size,"
            f" float lr, float stdp_lr) {{"
        )
        self.set_indent(1)
        self.emit(f"int ns = {nucleus_size};")
        self.emit(f"for (int t = BPTT_STEPS_{upper} - 1; t >= 0; t--) {{")
        self.set_indent(1)
        self.emit(f"for (int i = 0; i < {count}; i++) {{")
        self.set_indent(1)
        self.emit(f"Neuron_{neuron_type}* n = &{region_name}_neurons[i];")
        self.emit(f"memcpy(n->nucleus, {region_name}_ckpt[i][t], sizeof(n->nucleus));")
        self.emit("float target = (i < input_size) ? tanhf(input[i % ns]) : 0.0f;")
        self.emit(
            f"train_step_hybrid_{neuron_type}(n, input, target, lr, stdp_lr);"
        )
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.emit()

    def checkpoint_save_snippet(self, region_name: str, count: int, nucleus_size: int):
        """Lines to append at end of each timestep in run_region."""
        return [
            f"for (int ci = 0; ci < {count}; ci++) {{",
            f"    memcpy({region_name}_ckpt[ci][t], {region_name}_neurons[ci].nucleus,",
            f"        sizeof(float) * {nucleus_size});",
            "}",
        ]
