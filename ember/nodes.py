"""AST node definitions for Ember."""
from dataclasses import dataclass, field
from typing import Optional


# ---- expressions -----------------------------------------------------------

@dataclass
class IntLit:
    line: int
    value: int


@dataclass
class BoolLit:
    line: int
    value: bool


@dataclass
class Name:
    line: int
    name: str


@dataclass
class Unary:
    line: int
    op: str            # "-" or "not"
    operand: object


@dataclass
class Binary:
    line: int
    op: str            # + - * / % == != < <= > >= and or
    left: object
    right: object


@dataclass
class Call:
    line: int
    name: str
    args: list = field(default_factory=list)
    symbol: str = ""   # filled in by the checker: the function's symbol


@dataclass
class Index:
    line: int
    target: object     # an array expression
    index: object


@dataclass
class ArrayLit:
    line: int
    elems: list


# ---- statements ------------------------------------------------------------

@dataclass
class Let:
    """`mut name = expr`: always a new mutable binding."""
    line: int
    name: str
    expr: object


@dataclass
class Assign:
    """`name = expr`: declares an immutable binding, or reassigns an existing one."""
    line: int
    name: str
    expr: object


@dataclass
class IndexAssign:
    line: int
    target: object
    index: object
    value: object


@dataclass
class Return:
    line: int
    value: Optional[object]


@dataclass
class If:
    line: int
    branches: list                  # list of (condition, body)
    else_body: Optional[list]


@dataclass
class While:
    line: int
    cond: object
    body: list


@dataclass
class For:
    """`for name in range(start, stop):`. The stop bound is evaluated once."""
    line: int
    name: str
    start: object
    stop: object
    body: list


@dataclass
class Break:
    line: int


@dataclass
class Continue:
    line: int


@dataclass
class ExprStmt:
    line: int
    expr: object


# ---- top level -------------------------------------------------------------

@dataclass
class Param:
    line: int
    name: str
    type: str


@dataclass
class FuncDef:
    line: int
    name: str
    params: list
    ret: str                        # "i64", "bool", "[i64]", or "unit"
    body: Optional[list]            # None for an `extern def` (implemented in C)


@dataclass
class Program:
    funcs: list
