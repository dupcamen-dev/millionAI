from dataclasses import dataclass, field


class MIRType:
    pass


@dataclass
class MIRSpikeEvent:
    neuron_id: int
    time: int
    strength: float
    source_id: int = -1


@dataclass
class MIRSparseConnection:
    pre: int
    post: int
    weight: float
    delay: int = 1


@dataclass
class MIRFunction:
    name: str = ""
    params: list[tuple[str, str]] = field(default_factory=list)
    return_type: str = "void"
    body: list = field(default_factory=list)


@dataclass
class MIRModule:
    name: str = ""
    neurons: list = field(default_factory=list)
    regions: list = field(default_factory=list)
    datasets: list = field(default_factory=list)
    train_stmts: list = field(default_factory=list)
    infer_stmts: list = field(default_factory=list)
    event_driven: bool = True
    simulation_steps: int = 32
    functions: list[MIRFunction] = field(default_factory=list)
    quantization: str = "f32"
    learning_mode: str = "hybrid"


@dataclass
class MIRNeuron:
    name: str = ""
    nucleus_size: int = 16
    archive_levels: int = 3
    membrane_potential: float = 0.0
    membrane_threshold: str = "adaptive"
    refractory_period: float = 1.0
    dynamics: list = field(default_factory=list)
    learning_mode: str = "hybrid"
    loss_function: str = "mse"
    quantization: str = "f32"


@dataclass
class MIRRegion:
    name: str = ""
    neuron_type: str = ""
    neuron_count: int = 0
    connections: list = field(default_factory=list)
    sparse_connections: list[MIRSparseConnection] = field(default_factory=list)


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
    mode: str = "hybrid"
    stdp_lr: float = 0.01


@dataclass
class MIRInfer:
    region: str = ""
    input_var: str = ""
    output_var: str = ""


class IRBuilder:
    def __init__(self):
        self.module = MIRModule()

    def build(self, ast, **kwargs) -> MIRModule:
        self.module.quantization = kwargs.get("quantization", "f32")
        self.module.learning_mode = kwargs.get("learning_mode", "hybrid")
        for decl in ast.declarations:
            self.visit(decl)
        from compiler.ir.sparse_builder import build_sparse_connections

        for region in self.module.regions:
            if not region.sparse_connections:
                region.sparse_connections = build_sparse_connections(
                    region.neuron_count, region.connections
                )
        return self.module

    def visit(self, node):
        typename = type(node).__name__
        visitor = getattr(self, f"visit_{typename}", self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        pass

    def visit_FuncDef(self, node):
        params = [(p.name, p.type.name if p.type else "f32") for p in node.params]
        rt = node.return_type.name if node.return_type else "void"
        func = MIRFunction(
            name=node.name,
            params=params,
            return_type=rt,
            body=node.body.statements if node.body else [],
        )
        self.module.functions.append(func)

    def visit_NeuronDef(self, node):
        nuc_size = 16
        arch_levels = 3
        learning_mode = "hybrid"
        loss_function = "mse"
        quantization = "f32"
        if node.nucleus:
            if hasattr(node.nucleus, "levels"):
                arch_levels = node.nucleus.levels
                if hasattr(node.nucleus, "inner_type") and node.nucleus.inner_type:
                    if hasattr(node.nucleus.inner_type, "size"):
                        nuc_size = node.nucleus.inner_type.size
            elif hasattr(node.nucleus, "size"):
                nuc_size = node.nucleus.size

        mem_pot = 0.0
        mem_thr = "adaptive"
        mem_ref = 1.0
        if node.membrane:
            if node.membrane.potential and hasattr(node.membrane.potential, "value"):
                mem_pot = float(node.membrane.potential.value)
            if node.membrane.threshold:
                if hasattr(node.membrane.threshold, "name") and (
                    node.membrane.threshold.name == "adaptive"
                ):
                    mem_thr = "adaptive"
                elif hasattr(node.membrane.threshold, "value"):
                    mem_thr = str(node.membrane.threshold.value)
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
            learning_mode=learning_mode,
            loss_function=loss_function,
            quantization=quantization,
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
            conns.append(
                MIRConnection(
                    source=c.source,
                    target=c.target,
                    pattern=c.pattern,
                    sparsity=sparsity,
                    plasticity=c.plasticity,
                    branching=branching,
                )
            )
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
        mode = "hybrid"
        stdp_lr = 0.01
        for p in node.params:
            if p.key == "epochs":
                epochs = int(p.value.value) if hasattr(p.value, "value") else 1
            elif p.key in ("learning_rate", "rate"):
                lr = float(p.value.value) if hasattr(p.value, "value") else 0.01
            elif p.key == "rule":
                rule = p.value.name if hasattr(p.value, "name") else str(p.value)
            elif p.key in ("mode", "learning_mode"):
                mode = p.value.name if hasattr(p.value, "name") else str(p.value)
            elif p.key == "stdp_lr":
                stdp_lr = float(p.value.value) if hasattr(p.value, "value") else 0.01
            elif p.key == "quantization":
                mode = p.value.name if hasattr(p.value, "name") else str(p.value)
        train = MIRTrain(
            region=node.region,
            dataset=node.dataset,
            epochs=epochs,
            learning_rate=lr,
            rule=rule,
            mode=mode,
            stdp_lr=stdp_lr,
        )
        self.module.train_stmts.append(train)

    def visit_InferStmt(self, node):
        infer = MIRInfer(
            region=node.region,
            input_var=node.input,
            output_var=node.output,
        )
        self.module.infer_stmts.append(infer)
