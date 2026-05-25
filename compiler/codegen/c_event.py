"""Emit event-driven region runtime (spike queue + CSR synapses)."""

from __future__ import annotations

from compiler.ir.million_ir import MIRRegion, MIRSparseConnection


class CEventEmitter:
    """Generate event loop, spike queue, and CSR connectivity."""

    MAX_EVENTS = 10000

    def __init__(self, emit_fn, indent_setter, helpers):
        self.emit = emit_fn
        self.set_indent = indent_setter
        self.h = helpers

    def emit_globals(self):
        self.emit("/* ========= Event-Driven Runtime ========= */")
        self.emit("typedef struct {")
        self.emit("    int neuron_id;")
        self.emit("    int time;")
        self.emit("    float strength;")
        self.emit("    int source_id;")
        self.emit("} SpikeEvent;")
        self.emit()
        self.emit(f"#define MAX_EVENTS {self.MAX_EVENTS}")
        self.emit("typedef struct { int post; float weight; int delay; } Synapse;")
        self.emit()

    def emit_queue_helpers(self):
        self.emit("static int event_head = 0, event_tail = 0;")
        self.emit()
        self.emit("static int event_queue_full(int tail) {")
        self.set_indent(1)
        self.emit("return ((tail + 1) % MAX_EVENTS) == event_head;")
        self.set_indent(0)
        self.emit("}")
        self.emit()
        self.emit(
            "static void event_queue_push(SpikeEvent* q, int* tail, SpikeEvent ev) {"
        )
        self.set_indent(1)
        self.emit("if (event_queue_full(*tail)) return;")
        self.emit("int pos = *tail;")
        self.emit("q[pos] = ev;")
        self.emit("*tail = (*tail + 1) % MAX_EVENTS;")
        self.set_indent(0)
        self.emit("}")
        self.emit()
        self.emit(
            "static void event_queue_insert_sorted(SpikeEvent* q, int* head, int* tail,"
            " SpikeEvent ev) {"
        )
        self.set_indent(1)
        self.emit("if (event_queue_full(*tail)) return;")
        self.emit("if (*head == *tail) { event_queue_push(q, tail, ev); return; }")
        self.emit("int count = (*tail - *head + MAX_EVENTS) % MAX_EVENTS;")
        self.emit("int insert_at = *tail;")
        self.emit("for (int i = 0; i < count; i++) {")
        self.set_indent(1)
        self.emit("int idx = (*head + i) % MAX_EVENTS;")
        self.emit("if (q[idx].time > ev.time) { insert_at = idx; break; }")
        self.set_indent(0)
        self.emit("}")
        self.emit("/* shift tail forward */")
        self.emit("if (!event_queue_full(*tail)) {")
        self.set_indent(1)
        self.emit("int t = *tail;")
        self.emit("int stop = insert_at;")
        self.emit("while (t != stop) {")
        self.set_indent(1)
        self.emit("int prev = (t - 1 + MAX_EVENTS) % MAX_EVENTS;")
        self.emit("q[t] = q[prev];")
        self.emit("t = prev;")
        self.set_indent(0)
        self.emit("}")
        self.emit("q[insert_at] = ev;")
        self.emit("*tail = (*tail + 1) % MAX_EVENTS;")
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.emit()
        self.emit(
            "static void inject_input(SpikeEvent* q, int* head, int* tail,"
            " float* input, int n, int current_time) {"
        )
        self.set_indent(1)
        self.emit("for (int i = 0; i < n; i++) {")
        self.set_indent(1)
        self.emit("if (fabsf(input[i]) < 1e-6f) continue;")
        self.emit("SpikeEvent ev = { .neuron_id = i, .time = current_time,")
        self.emit("    .strength = input[i], .source_id = -1 };")
        self.emit("event_queue_insert_sorted(q, head, tail, ev);")
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.emit()

    def emit_region_csr(self, region: MIRRegion):
        name = region.name
        count = region.neuron_count
        edges = region.sparse_connections
        by_pre: dict[int, list[MIRSparseConnection]] = {i: [] for i in range(count)}
        for e in edges:
            by_pre[e.pre].append(e)

        self.emit(f"/* CSR synapses: {name} */")
        self.emit(f"static Synapse {name}_syn_data[] = {{")
        for pre in range(count):
            for syn in by_pre[pre]:
                self.emit(
                    f"    {{ {syn.post}, {syn.weight:.6f}f, {syn.delay} }},"
                )
        self.emit("};")
        self.emit(f"static int {name}_syn_offsets[{count + 1}] = {{")
        offset = 0
        parts = ["0"]
        for pre in range(count):
            offset += len(by_pre[pre])
            parts.append(str(offset))
        self.emit("    " + ", ".join(parts))
        self.emit("};")
        self.emit()

    def emit_run_region(
        self,
        region: MIRRegion,
        process_name: str,
        steps: int,
    ):
        name = region.name
        nt = region.neuron_type
        count = region.neuron_count
        upper = name.upper()

        self.emit_region_csr(region)
        self.emit(f"static SpikeEvent {name}_event_q[MAX_EVENTS];")
        self.emit()
        self.emit(f"void run_region_{name}(int steps) {{")
        self.set_indent(1)
        self.emit(f"for (int t = 0; t < steps; t++) {{")
        self.set_indent(1)
        self.emit("while (event_head != event_tail) {")
        self.set_indent(1)
        self.emit(f"SpikeEvent ev = {name}_event_q[event_head];")
        self.emit("if (ev.time != t) break;")
        self.emit("event_head = (event_head + 1) % MAX_EVENTS;")
        self.emit(f"Neuron_{nt}* n = &{name}_neurons[ev.neuron_id];")
        self.emit("if (n->mem.refr_counter > 0) continue;")
        self.emit("float strength = ev.strength;")
        self.emit(
            f"int fired = process_{nt}(n, &strength, 1);"
        )
        self.emit("if (!fired) continue;")
        self.emit(f"int s0 = {name}_syn_offsets[ev.neuron_id];")
        self.emit(f"int s1 = {name}_syn_offsets[ev.neuron_id + 1];")
        self.emit("for (int s = s0; s < s1; s++) {")
        self.set_indent(1)
        self.emit(f"Synapse syn = {name}_syn_data[s];")
        self.emit("SpikeEvent post = {")
        self.emit("    .neuron_id = syn.post,")
        self.emit("    .time = t + syn.delay,")
        self.emit("    .strength = syn.weight * n->output,")
        self.emit("    .source_id = ev.neuron_id")
        self.emit("};")
        self.emit(
            f"event_queue_insert_sorted({name}_event_q, &event_head, &event_tail, post);"
        )
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.emit("/* decay refractory counters each tick */")
        self.emit(f"for (int i = 0; i < NUM_NEURONS_{upper}; i++) {{")
        self.set_indent(1)
        self.emit(f"if ({name}_neurons[i].mem.refr_counter > 0)")
        self.emit(f"    {name}_neurons[i].mem.refr_counter--;")
        self.set_indent(0)
        self.emit("}")
        self.emit(f"/* BPTT: save nucleus checkpoints at time t */")
        self.emit(f"for (int ci = 0; ci < {count}; ci++) {{")
        self.set_indent(1)
        self.emit(
            f"memcpy({name}_ckpt[ci][t], {name}_neurons[ci].nucleus,"
            f" sizeof({name}_neurons[0].nucleus));"
        )
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.set_indent(0)
        self.emit("}")
        self.emit()

    def emit_step_compat(
        self,
        region: MIRRegion,
        input_size: int,
        steps: int = 8,
    ):
        """Dense-compatible step_region wrapper over event runtime."""
        name = region.name
        count = region.neuron_count
        self.emit(
            f"void step_region_{name}(float* input, int input_size, float* output) {{"
        )
        self.set_indent(1)
        self.emit("event_head = 0;")
        self.emit("event_tail = 0;")
        self.emit(f"inject_input({name}_event_q, &event_head, &event_tail, input,")
        self.emit(f"    input_size < {input_size} ? input_size : {input_size}, 0);")
        self.emit(f"run_region_{name}({steps});")
        self.emit(f"for (int i = 0; i < {count}; i++)")
        self.emit(f"    output[i] = {name}_neurons[i].output;")
        self.set_indent(0)
        self.emit("}")
        self.emit()
