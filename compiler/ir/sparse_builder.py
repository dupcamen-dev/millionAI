"""Build deterministic sparse synapse lists for MIR regions."""

from __future__ import annotations

import random

from compiler.ir.million_ir import MIRConnection, MIRSparseConnection


def build_sparse_connections(
    neuron_count: int,
    connections: list[MIRConnection],
    *,
    seed: int = 42,
) -> list[MIRSparseConnection]:
    """Create CSR-ready sparse edges from region connect blocks."""
    if neuron_count <= 0:
        return []

    sparsity = 0.01
    branching = 4
    delay = 1
    pattern = ""
    for conn in connections:
        sparsity = conn.sparsity
        branching = max(1, conn.branching)
        pattern = conn.pattern
        if conn.plasticity.upper() == "STDP":
            delay = 1

    if not connections:
        return [
            MIRSparseConnection(pre=i, post=i, weight=0.05, delay=1)
            for i in range(neuron_count)
        ]

    rng = random.Random(seed)
    edges: list[MIRSparseConnection] = []
    for pre in range(neuron_count):
        local_targets = 0
        for post in range(neuron_count):
            if pattern == "hierarchical" and post // branching != pre // branching:
                continue
            if rng.random() < sparsity or (pre == post and rng.random() < 0.3):
                weight = (rng.random() * 2.0 - 1.0) * 0.1
                edges.append(
                    MIRSparseConnection(
                        pre=pre,
                        post=post,
                        weight=weight,
                        delay=delay,
                    )
                )
                local_targets += 1
                if local_targets >= branching * 2:
                    break
    return edges
