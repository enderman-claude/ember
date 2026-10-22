"""Semantic checks: entry point, name resolution, and static types (i64, bool, unit)."""
from dataclasses import dataclass
from .errors import CompileError
from . import nodes as n

I64_MIN, I64_MAX = -(2 ** 63), 2 ** 63 - 1


@dataclass
class Sig:
    params: list
    ret: str


# Builtins are implemented by the C runtime (ember/runtime/ember_rt.c).
BUILTINS = {"print": Sig(["i64"], "unit")}


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

    def check(self):
        check_entry_point(self.prog)
        for f in self.prog.funcs:
            if f.name in BUILTINS:
                raise CompileError(f.line, f"{f.name!r} is a builtin and cannot be redefined")
            if f.name in self.sigs:
                raise CompileError(f.line, f"function {f.name!r} is already defined")
            self.sigs[f.name] = Sig([p.type for p in f.params], f.ret)
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

    # -- statements -----------------------------------------------------------
    def check_stmt(self, s):
        if isinstance(s, n.Let):
            ty = self.expr_type(s.expr)
            if s.name in self.scopes[-1]:
                raise CompileError(s.line, f"{s.name!r} is already declared in this scope")
            self.scopes[-1][s.name] = (ty, True)

        elif isinstance(s, n.Assign):
            ty = self.expr_type(s.expr)
            found = self.lookup(s.name)
            if found is None:
                self.scopes[-1][s.name] = (ty, False)
                return
            cur_ty, mutable = found
            if not mutable:
                raise CompileError(
                    s.line, f"cannot assign to immutable {s.name!r} (declare it with `mut`)")
            self.require(ty, cur_ty, s.line, f"assignment to {s.name!r}")

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
            self.check_block(s.body)

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
        if isinstance(e, n.Call):
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
            return sig.ret
        raise CompileError(getattr(e, "line", 0), f"internal error: unknown expression {e!r}")


def check(prog: n.Program):
    Checker(prog).check()
