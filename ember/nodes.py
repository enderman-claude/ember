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
    ret: str                        # "i64", "bool", or "unit"
    body: list


@dataclass
class Program:
    funcs: list
