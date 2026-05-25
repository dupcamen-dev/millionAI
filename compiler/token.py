from enum import Enum, auto


class TokenType(Enum):
    EOF = auto()
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()

    KEYWORD = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    FLOAT = auto()
    STRING = auto()

    LBRACE = auto()
    RBRACE = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COLON = auto()
    SEMICOLON = auto()
    COMMA = auto()
    ARROW = auto()
    FAT_ARROW = auto()
    DOT = auto()
    EQUALS = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    PIPE = auto()
    AMPERSAND = auto()
    LESS = auto()
    GREATER = auto()
    LE = auto()
    GE = auto()
    EQEQ = auto()
    NE = auto()
    BANG = auto()
    DOTDOT = auto()
    ANDAND = auto()
    PIPEPIPE = auto()


KEYWORDS = {
    "neuron", "region", "data", "train", "infer", "connect", "use",
    "archive", "state", "membrane", "dynamics",
    "adaptive", "hebbian", "stdp", "sparse", "hierarchical", "in",
    "self", "input", "output", "on", "as",
    "epochs", "rule", "source", "shape", "plasticity",
    "branching", "sparsity", "potential", "threshold",
    "refractory", "learning_rate", "batch_size",
    "true", "false", "and", "or", "not",
    "if", "else", "for", "while", "return",
    "let", "fn", "int", "bool", "string", "tensor", "list",
    "mode", "online", "quantization",
    "int8", "binary",
}


class Token:
    __slots__ = ("type", "value", "line", "col")

    def __init__(self, type_: TokenType, value: object, line: int, col: int):
        self.type = type_
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:{self.col})"
