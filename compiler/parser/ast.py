from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    line: int = 0
    col: int = 0


@dataclass
class Literal(Node):
    value: Any = None


@dataclass
class Identifier(Node):
    name: str = ""


@dataclass
class TypeRef(Node):
    name: str = ""
    params: list[Node] = field(default_factory=list)


@dataclass
class ArchiveType(Node):
    inner_type: Node = None
    levels: int = 3


@dataclass
class StateType(Node):
    size: int = 16


@dataclass
class Call(Node):
    name: str = ""
    args: list[Node] = field(default_factory=list)


@dataclass
class BinaryOp(Node):
    left: Node = None
    op: str = ""
    right: Node = None


@dataclass
class UnaryOp(Node):
    op: str = ""
    operand: Node = None


@dataclass
class Assignment(Node):
    target: str = ""
    value: Node = None


@dataclass
class MembraneDef(Node):
    potential: Node = None
    threshold: Node = None
    refractory: Node = None


@dataclass
class DynamicsDef(Node):
    statements: list[Node] = field(default_factory=list)


@dataclass
class NeuronDef(Node):
    name: str = ""
    nucleus: Node = None
    membrane: MembraneDef = None
    dynamics: DynamicsDef = None


@dataclass
class ConnectionDef(Node):
    source: str = ""
    target: str = ""
    pattern: str = ""
    sparsity: Node = None
    plasticity: str = ""
    branching: Node = None


@dataclass
class RegionDef(Node):
    name: str = ""
    neuron_type: str = ""
    count: int = 0
    connections: list[ConnectionDef] = field(default_factory=list)


@dataclass
class DataDef(Node):
    name: str = ""
    source: str = ""
    shape: list[int] = field(default_factory=list)


@dataclass
class ParamAssign(Node):
    key: str = ""
    value: Node = None


@dataclass
class TrainStmt(Node):
    region: str = ""
    dataset: str = ""
    params: list[ParamAssign] = field(default_factory=list)


@dataclass
class InferStmt(Node):
    region: str = ""
    input: str = ""
    output: str = ""


@dataclass
class Program(Node):
    declarations: list[Node] = field(default_factory=list)
