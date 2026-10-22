"""Semantic checks: entry point, name resolution, and static types (i64, bool, [i64], unit)."""
from dataclasses import dataclass
from .errors import CompileError
from . import nodes as n

I64_MIN, I64_MAX = -(2 ** 63), 2 ** 63 - 1
ARRAY = "[i64]"


@dataclass
class Sig:
    params: list
    ret: str
    symbol: str


# Builtins implemented by the C runtime (ember/runtime/ember_rt.c).
BUILTINS = {
    "alloc": Sig(["i64"], ARRAY, "ember_alloc"),
    "free": Sig([ARRAY], "unit", "ember_free"),
    "len": Sig([ARRAY], "i64", "ember_len"),
    "read_int": Sig([], "i64", "ember_read_int"),
    "input_ended": Sig([], "bool", "ember_input_ended"),
    "put_byte": Sig(["i64"], "unit", "ember_put_byte"),
}
# print() is overloaded on its argument type.
PRINT_SYMBOLS = {"i64": "ember_print_i64", "bool": "ember_print_bool"}
RESERVED = set(BUILTINS) | {"print"}


def check_entry_point(prog: n.Program):
    """Exactly one parameterless `def main()` must exist."""
    mains = [f for f in prog.funcs if f.name == "main"]
    if not mains:
        raise CompileError(1, "program has no entry point: define `def main():`")
    if len(mains) > 1:
        lines = ", ".join(str(f.line) for f in mains)
        raise CompileError(mains[1].line, f"multiple definitions of main() at lines {lines}")
    main = mains[0]
    if main.params:
        raise CompileError(main.line, "main() must take no parameters")
    if main.ret != "unit":
        raise CompileError(main.line, "main() must not return a value")


def always_returns(block) -> bool:
    for s in block:
        if isinstance(s, n.Return):
            return True
        if (isinstance(s, n.If) and s.else_body is not None
                and all(always_returns(b) for _, b in s.branches)
                and always_returns(s.else_body)):
            return True
    return False


class Checker:
    def __init__(self, prog: n.Program):
        self.prog = prog
        self.sigs = dict(BUILTINS)
        self.scopes = []
        self.ret = "unit"
        self.fn_name = ""
        self.loop_depth = 0

    def check(self):
        check_entry_point(self.prog)
        for f in self.prog.funcs:
            if f.name in RESERVED:
                raise CompileError(f.line, f"{f.name!r} is a builtin and cannot be redefined")
            if f.name in self.sigs:
                raise CompileError(f.line, f"function {f.name!r} is already defined")
            self.sigs[f.name] = Sig([p.type for p in f.params], f.ret, f"em_{f.name}")
        for f in self.prog.funcs:
            self.check_function(f)

    # -- scopes ---------------------------------------------------------------
    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def check_function(self, f):
        self.fn_name = f.name
        self.ret = f.ret
        self.loop_depth = 0
        self.scopes = [{}]
        for p in f.params:
            if p.name in self.scopes[0]:
                raise CompileError(p.line, f"duplicate parameter {p.name!r}")
            self.scopes[0][p.name] = (p.type, False)
        self.check_block(f.body)
        if f.ret != "unit" and not always_returns(f.body):
            raise CompileError(
                f.line, f"function {f.name!r} may finish without returning a value of type {f.ret}")

    def check_block(self, stmts):
        self.scopes.append({})
        for s in stmts:
            self.check_stmt(s)
        self.scopes.pop()

    def check_loop_body(self, body):
        self.loop_depth += 1
        self.check_block(body)
        self.loop_depth -= 1

    # -- statements -----------------------------------------------------------
    def value_type(self, e, name):
        ty = self.expr_type(e)
        if ty == "unit":
            raise CompileError(e.line, f"cannot bind {name!r}: the expression has no value")
        return ty

    def index_check(self, target, index, line):
        t = self.expr_type(target)
        if t != ARRAY:
            raise CompileError(line, f"cannot index a value of type {t}")
        self.require(self.expr_type(index), "i64", line, "array index")

    def check_stmt(self, s):
        if isinstance(s, n.Let):
            ty = self.value_type(s.expr, s.name)
            if s.name in self.scopes[-1]:
                raise CompileError(s.line, f"{s.name!r} is already declared in this scope")
            self.scopes[-1][s.name] = (ty, True)

        elif isinstance(s, n.Assign):
            ty = self.value_type(s.expr, s.name)
            found = self.lookup(s.name)
            if found is None:
                self.scopes[-1][s.name] = (ty, False)
                return
            cur_ty, mutable = found
            if not mutable:
                raise CompileError(
                    s.line, f"cannot assign to immutable {s.name!r} (declare it with `mut`)")
            self.require(ty, cur_ty, s.line, f"assignment to {s.name!r}")

        elif isinstance(s, n.IndexAssign):
            self.index_check(s.target, s.index, s.line)
            self.require(self.expr_type(s.value), "i64", s.line, "array element assignment")

        elif isinstance(s, n.Return):
            if s.value is None:
                if self.ret != "unit":
                    raise CompileError(s.line, f"return without a value in function returning {self.ret}")
            else:
                if self.ret == "unit":
                    raise CompileError(s.line, f"function {self.fn_name!r} returns nothing; remove the value")
                self.require(self.expr_type(s.value), self.ret, s.line, "return value")

        elif isinstance(s, n.If):
            for cond, body in s.branches:
                self.require(self.expr_type(cond), "bool", s.line, "if condition")
                self.check_block(body)
            if s.else_body is not None:
                self.check_block(s.else_body)

        elif isinstance(s, n.While):
            self.require(self.expr_type(s.cond), "bool", s.line, "while condition")
            self.check_loop_body(s.body)

        elif isinstance(s, n.For):
            self.require(self.expr_type(s.start), "i64", s.line, "range start")
            self.require(self.expr_type(s.stop), "i64", s.line, "range stop")
            self.scopes.append({s.name: ("i64", False)})
            self.check_loop_body(s.body)
            self.scopes.pop()

        elif isinstance(s, (n.Break, n.Continue)):
            if self.loop_depth == 0:
                kw = "break" if isinstance(s, n.Break) else "continue"
                raise CompileError(s.line, f"'{kw}' outside of a loop")

        elif isinstance(s, n.ExprStmt):
            self.expr_type(s.expr)

    # -- expressions ----------------------------------------------------------
    def require(self, got, want, line, what):
        if got != want:
            raise CompileError(line, f"type mismatch in {what}: expected {want}, found {got}")

    def expr_type(self, e) -> str:
        if isinstance(e, n.IntLit):
            if not I64_MIN <= e.value <= I64_MAX:
                raise CompileError(e.line, f"integer literal {e.value} does not fit in i64")
            return "i64"

        if isinstance(e, n.BoolLit):
            return "bool"

        if isinstance(e, n.Name):
            found = self.lookup(e.name)
            if found is None:
                if e.name in self.sigs:
                    raise CompileError(e.line, f"{e.name!r} is a function; call it with parentheses")
                raise CompileError(e.line, f"undefined name {e.name!r}")
            return found[0]

        if isinstance(e, n.Unary):
            t = self.expr_type(e.operand)
            if e.op == "-":
                self.require(t, "i64", e.line, "unary '-'")
                return "i64"
            self.require(t, "bool", e.line, "'not'")
            return "bool"

        if isinstance(e, n.Binary):
            lt, rt = self.expr_type(e.left), self.expr_type(e.right)
            if e.op in ("and", "or"):
                self.require(lt, "bool", e.line, f"'{e.op}' operand")
                self.require(rt, "bool", e.line, f"'{e.op}' operand")
                return "bool"
            if e.op in ("==", "!="):
                if lt != rt or lt == "unit":
                    raise CompileError(e.line, f"cannot compare {lt} with {rt}")
                return "bool"
            self.require(lt, "i64", e.line, f"left operand of '{e.op}'")
            self.require(rt, "i64", e.line, f"right operand of '{e.op}'")
            return "bool" if e.op in ("<", "<=", ">", ">=") else "i64"

        if isinstance(e, n.Index):
            self.index_check(e.target, e.index, e.line)
            return "i64"

        if isinstance(e, n.ArrayLit):
            if not e.elems:
                raise CompileError(e.line, "empty array literals are not allowed; use alloc(n)")
            for el in e.elems:
                self.require(self.expr_type(el), "i64", e.line, "array literal element")
            return ARRAY

        if isinstance(e, n.Call):
            if e.name == "print":
                if len(e.args) != 1:
                    raise CompileError(e.line, "print() takes exactly 1 argument")
                t = self.expr_type(e.args[0])
                if t not in PRINT_SYMBOLS:
                    raise CompileError(e.line, f"print() takes i64 or bool, found {t}")
                e.symbol = PRINT_SYMBOLS[t]
                return "unit"
            sig = self.sigs.get(e.name)
            if sig is None:
                raise CompileError(e.line, f"undefined function {e.name!r}")
            if len(e.args) != len(sig.params):
                raise CompileError(
                    e.line, f"{e.name}() takes {len(sig.params)} argument(s), got {len(e.args)}")
            if len(sig.params) > 6:
                raise CompileError(e.line, f"{e.name}(): at most 6 parameters are supported")
            for arg, want in zip(e.args, sig.params):
                self.require(self.expr_type(arg), want, e.line, f"argument to {e.name}()")
            e.symbol = sig.symbol
            return sig.ret

        raise CompileError(getattr(e, "line", 0), f"internal error: unknown expression {e!r}")


def check(prog: n.Program):
    Checker(prog).check()
