from dataclasses import dataclass, field
from typing import Any


class MIRType:
    pass


@dataclass
class MIRModule:
    name: str = ""
    neurons: list = field(default_factory=list)
    regions: list = field(default_factory=list)
    datasets: list = field(default_factory=list)
    train_stmts: list = field(default_factory=list)
    infer_stmts: list = field(default_factory=list)


@dataclass
class MIRNeuron:
    name: str = ""
    nucleus_size: int = 16
    archive_levels: int = 3
    membrane_potential: float = 0.0
    membrane_threshold: str = "adaptive"
    refractory_period: float = 1.0
    dynamics: list = field(default_factory=list)


@dataclass
class MIRRegion:
    name: str = ""
    neuron_type: str = ""
    neuron_count: int = 0
    connections: list = field(default_factory=list)


@dataclass
class MIRConnection:
    source: str = ""
    target: str = ""
    pattern: str = ""
    sparsity: float = 0.01
    plasticity: str = ""
    branching: int = 4


@dataclass
class MIRDataset:
    name: str = ""
    source: str = ""
    shape: list = field(default_factory=list)


@dataclass
class MIRTrain:
    region: str = ""
    dataset: str = ""
    epochs: int = 1
    learning_rate: float = 0.01
    rule: str = "hebbian"


@dataclass
class MIRInfer:
    region: str = ""
    input_var: str = ""
    output_var: str = ""


class IRBuilder:
    def __init__(self):
        self.module = MIRModule()

    def build(self, ast) -> MIRModule:
        for decl in ast.declarations:
            self.visit(decl)
        return self.module

    def visit(self, node):
        typename = type(node).__name__
        visitor = getattr(self, f"visit_{typename}", self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        pass

    def visit_NeuronDef(self, node):
        nuc_size = 16
        arch_levels = 3
        if node.nucleus:
            if hasattr(node.nucleus, "size"):
                nuc_size = node.nucleus.size
            if hasattr(node.nucleus, "levels"):
                arch_levels = node.nucleus.levels

        mem_pot = 0.0
        mem_thr = "adaptive"
        mem_ref = 1.0
        if node.membrane:
            if node.membrane.potential and hasattr(node.membrane.potential, "value"):
                mem_pot = float(node.membrane.potential.value)
            if node.membrane.threshold:
                if hasattr(node.membrane.threshold, "name") and node.membrane.threshold.name == "adaptive":
                    mem_thr = "adaptive"
            if node.membrane.refractory and hasattr(node.membrane.refractory, "value"):
                mem_ref = float(str(node.membrane.refractory.value).replace("ms", ""))

        dynamics = []
        if node.dynamics:
            dynamics = node.dynamics.statements

        neuron = MIRNeuron(
            name=node.name,
            nucleus_size=nuc_size,
            archive_levels=arch_levels,
            membrane_potential=mem_pot,
            membrane_threshold=mem_thr,
            refractory_period=mem_ref,
            dynamics=dynamics,
        )
        self.module.neurons.append(neuron)

    def visit_RegionDef(self, node):
        conns = []
        for c in node.connections:
            sparsity = 0.01
            if c.sparsity and hasattr(c.sparsity, "value"):
                sparsity = float(c.sparsity.value)
            branching = 4
            if c.branching and hasattr(c.branching, "value"):
                branching = int(c.branching.value)
            conns.append(MIRConnection(
                source=c.source, target=c.target,
                pattern=c.pattern, sparsity=sparsity,
                plasticity=c.plasticity, branching=branching,
            ))
        region = MIRRegion(
            name=node.name,
            neuron_type=node.neuron_type,
            neuron_count=node.count,
            connections=conns,
        )
        self.module.regions.append(region)

    def visit_DataDef(self, node):
        ds = MIRDataset(
            name=node.name,
            source=node.source,
            shape=node.shape,
        )
        self.module.datasets.append(ds)

    def visit_TrainStmt(self, node):
        epochs = 1
        lr = 0.01
        rule = "hebbian"
        for p in node.params:
            if p.key == "epochs":
                epochs = int(p.value.value) if hasattr(p.value, "value") else 1
            elif p.key == "learning_rate" or p.key == "rate":
                lr = float(p.value.value) if hasattr(p.value, "value") else 0.01
            elif p.key == "rule":
                rule = p.value.name if hasattr(p.value, "name") else str(p.value)
        train = MIRTrain(
            region=node.region,
            dataset=node.dataset,
            epochs=epochs,
            learning_rate=lr,
            rule=rule,
        )
        self.module.train_stmts.append(train)

    def visit_InferStmt(self, node):
        infer = MIRInfer(
            region=node.region,
            input_var=node.input,
            output_var=node.output,
        )
        self.module.infer_stmts.append(infer)
