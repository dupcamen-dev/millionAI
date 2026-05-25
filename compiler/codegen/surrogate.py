"""Surrogate gradient functions for spike neuron training."""


class SurrogateGradientEmitter:
    """Emit surrogate gradient C functions for differentiable spike approximation."""

    def __init__(self, emit_fn):
        self.emit = emit_fn

    def emit_block(self):
        self.emit("/* ========= Surrogate Gradients ========= */")
        self.emit("")
        self._emit_fast_sigmoid()
        self._emit_super_spike()
        self._emit_exponential()

    def _emit_fast_sigmoid(self):
        # Fast sigmoid surrogate: d(spike)/dpot = 1 / (1 + beta*|pot|)^2
        self.emit("""
void surrogate_fast_sigmoid(float* potentials, float* grad, int n, float beta) {
    for (int i = 0; i < n; i++) {
        float absp = fabsf(potentials[i]);
        float denom = 1.0f + beta * absp;
        grad[i] = 1.0f / (denom * denom);
    }
}
""")

    def _emit_super_spike(self):
        # SuperSpike: d(spike)/dpot = beta / (1 + beta*|pot|)^2
        self.emit("""
void surrogate_super_spike(float* potentials, float* grad, int n, float beta) {
    for (int i = 0; i < n; i++) {
        float absp = fabsf(potentials[i]);
        float denom = 1.0f + beta * absp;
        grad[i] = beta / (denom * denom);
    }
}
""")

    def _emit_exponential(self):
        # Exponential surrogate: d(spike)/dpot = beta * exp(-beta * |pot - threshold|)
        self.emit("""
void surrogate_exponential(float* potentials, float* grad, int n, 
                           float beta, float threshold) {
    for (int i = 0; i < n; i++) {
        float diff = fabsf(potentials[i] - threshold);
        grad[i] = beta * expf(-beta * diff);
    }
}
""")
