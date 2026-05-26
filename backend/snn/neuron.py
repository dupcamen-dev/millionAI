import math
import numpy as np

from .encoding import archive_unfold, archive_compress, ARCHIVE_N

class TradingNeuron:
    def __init__(self, nucleus=None, nucleus_size=ARCHIVE_N):
        if nucleus is not None:
            self.nucleus = np.array(nucleus, dtype=np.float32)
        else:
            fan = nucleus_size + nucleus_size
            scale = math.sqrt(6.0 / fan)
            self.nucleus = np.random.uniform(-scale, scale, nucleus_size).astype(np.float32)
        self.bias = 1.0
        self.potential = 0.0
        self.threshold = 0.5
        self.output = 0.0
        self.refr = 0
        self.decay = 0.99
        self.eligibility = np.zeros(nucleus_size, dtype=np.float32)

    def forward(self, input_vec):
        if self.refr > 0:
            self.refr -= 1
            self.output = 0.0
            return
        SENSORY = len(input_vec)
        # Level 1: nucleus[64] -> unfold -> compress -> features[64]
        unfolded1 = archive_unfold(self.nucleus, 1)
        features = archive_compress(unfolded1, ARCHIVE_N)
        # Level 2: features[64] -> unfold -> compress -> state[64]
        unfolded2 = archive_unfold(features, 2)
        state = archive_compress(unfolded2, ARCHIVE_N)
        delta = np.dot(input_vec[:SENSORY], state[:SENSORY]) / float(SENSORY) + self.bias
        self.potential += delta
        if self.potential >= self.threshold:
            self.output = self.potential
            self.potential = 0.0
            self.refr = 0
            self.threshold = 0.5 + (self.threshold - 0.5) * 0.9 + 0.1 * abs(self.output)
        else:
            self.output = 0.0
            self.potential *= self.decay

    def state_dict(self):
        return {
            "nucleus": self.nucleus.tolist(),
            "potential": float(self.potential),
            "threshold": float(self.threshold),
            "eligibility": self.eligibility.tolist(),
        }

    def load_state(self, data):
        self.nucleus = np.array(data["nucleus"], dtype=np.float32)
        self.potential = data.get("potential", 0.0)
        self.threshold = data.get("threshold", 0.5)
        self.eligibility = np.array(data.get("eligibility", []), dtype=np.float32)
