"""Recursive-descent parser. Produces nodes from ember.nodes."""
from .errors import CompileError
from .lexer import tokenize
from . import nodes as n

CMP_OPS = ("==", "!=", "<", "<=", ">", ">=")
SCALAR_TYPES = ("i64", "bool")


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    # -- token helpers --------------------------------------------------------
    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def at(self, kind):
        return self.peek().kind == kind

    def advance(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind, what=None):
        t = self.peek()
        if t.kind != kind:
            found = t.value if t.value else t.kind.lower()
            raise CompileError(t.line, f"expected {what or repr(kind)}, found {found!r}", t.col)
        return self.advance()

    def skip_newlines(self):
        while self.at("NEWLINE"):
            self.advance()

    # -- top level ------------------------------------------------------------
    def parse_program(self):
        funcs = []
        self.skip_newlines()
        while not self.at("EOF"):
            if self.at("def"):
                funcs.append(self.parse_def())
            else:
                t = self.peek()
                raise CompileError(
                    t.line,
                    "top-level statements are not allowed; only `def` may appear here "
                    "(move executable code into main())",
                    t.col,
                )
            self.skip_newlines()
        return n.Program(funcs)

    def parse_def(self):
        kw = self.expect("def")
        name = self.expect("NAME", "function name").value
        self.expect("(", "'('")
        params = []
        if not self.at(")"):
            while True:
                pt = self.expect("NAME", "parameter name")
                self.expect(":", "':' after parameter name")
                params.append(n.Param(pt.line, pt.value, self.parse_type()))
                if not self.at(","):
                    break
                self.advance()
        self.expect(")", "')'")
        ret = "unit"
        if self.at("->"):
            self.advance()
            ret = self.parse_type()
        self.expect(":", "':' before function body")
        return n.FuncDef(kw.line, name, params, ret, self.parse_block())

    def parse_type(self):
        if self.at("["):
            self.advance()
            elem = self.expect("NAME", "element type")
            if elem.value != "i64":
                raise CompileError(elem.line, "only arrays of i64 are supported; write [i64]", elem.col)
            self.expect("]", "']'")
            return "[i64]"
        t = self.expect("NAME", "type name")
        if t.value not in SCALAR_TYPES:
            raise CompileError(t.line, f"unknown type {t.value!r} (expected i64, bool or [i64])", t.col)
        return t.value

    # -- statements -----------------------------------------------------------
    def parse_block(self):
        self.expect("NEWLINE", "end of line")
        self.expect("INDENT", "an indented block")
        stmts = []
        while not self.at("DEDENT") and not self.at("EOF"):
            if self.at("NEWLINE"):
                self.advance()
                continue
            stmts.append(self.parse_stmt())
        if self.at("DEDENT"):
            self.advance()
        return stmts

    def parse_stmt(self):
        t = self.peek()
        k = t.kind
        if k == "if":
            return self.parse_if()
        if k == "while":
            self.advance()
            cond = self.parse_expr()
            self.expect(":", "':' after while condition")
            return n.While(t.line, cond, self.parse_block())
        if k == "for":
            return self.parse_for()
        if k == "return":
            self.advance()
            value = None if self.at("NEWLINE") else self.parse_expr()
            self.expect("NEWLINE")
            return n.Return(t.line, value)
        if k in ("break", "continue"):
            self.advance()
            self.expect("NEWLINE")
            return n.Break(t.line) if k == "break" else n.Continue(t.line)
        if k == "mut":
            self.advance()
            name = self.expect("NAME", "variable name").value
            self.expect("=", "'=' in mut declaration")
            expr = self.parse_expr()
            self.expect("NEWLINE")
            return n.Let(t.line, name, expr)
        if k == "NAME" and self.peek(1).kind == "=":
            self.advance()
            self.advance()
            expr = self.parse_expr()
            self.expect("NEWLINE")
            return n.Assign(t.line, t.value, expr)
        expr = self.parse_expr()
        if self.at("="):
            eq = self.advance()
            if not isinstance(expr, n.Index):
                raise CompileError(eq.line, "the left side of '=' must be a name or an array element", eq.col)
            value = self.parse_expr()
            self.expect("NEWLINE")
            return n.IndexAssign(t.line, expr.target, expr.index, value)
        self.expect("NEWLINE")
        return n.ExprStmt(t.line, expr)

    def parse_if(self):
        t = self.advance()  # 'if'
        cond = self.parse_expr()
        self.expect(":", "':' after if condition")
        branches = [(cond, self.parse_block())]
        while self.at("elif"):
            self.advance()
            c = self.parse_expr()
            self.expect(":", "':' after elif condition")
            branches.append((c, self.parse_block()))
        else_body = None
        if self.at("else"):
            self.advance()
            self.expect(":", "':' after else")
            else_body = self.parse_block()
        return n.If(t.line, branches, else_body)

    def parse_for(self):
        t = self.advance()  # 'for'
        var = self.expect("NAME", "loop variable").value
        self.expect("in", "'in'")
        r = self.expect("NAME", "'range'")
        if r.value != "range":
            raise CompileError(r.line, "only `for x in range(...)` loops are supported", r.col)
        self.expect("(", "'('")
        args = [self.parse_expr()]
        if self.at(","):
            self.advance()
            args.append(self.parse_expr())
        self.expect(")", "')'")
        if len(args) == 1:
            start, stop = n.IntLit(t.line, 0), args[0]
        else:
            start, stop = args
        self.expect(":", "':' after for header")
        return n.For(t.line, var, start, stop, self.parse_block())

    # -- expressions (lowest to highest precedence) ----------------------------
    def parse_expr(self):
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.at("or"):
            t = self.advance()
            left = n.Binary(t.line, "or", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.at("and"):
            t = self.advance()
            left = n.Binary(t.line, "and", left, self.parse_not())
        return left

    def parse_not(self):
        if self.at("not"):
            t = self.advance()
            return n.Unary(t.line, "not", self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self):
        left = self.parse_add()
        if self.peek().kind in CMP_OPS:   # comparisons do not chain
            t = self.advance()
            left = n.Binary(t.line, t.kind, left, self.parse_add())
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.peek().kind in ("+", "-"):
            t = self.advance()
            left = n.Binary(t.line, t.kind, left, self.parse_mul())
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.peek().kind in ("*", "/", "%"):
            t = self.advance()
            left = n.Binary(t.line, t.kind, left, self.parse_unary())
        return left

    def parse_unary(self):
        if self.at("-"):
            t = self.advance()
            return n.Unary(t.line, "-", self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        e = self.parse_primary()
        while self.at("["):
            t = self.advance()
            index = self.parse_expr()
            self.expect("]", "']'")
            e = n.Index(t.line, e, index)
        return e

    def parse_expr_list(self, closer):
        items = []
        while not self.at(closer):
            items.append(self.parse_expr())
            if not self.at(","):
                break
            self.advance()
        return items

    def parse_primary(self):
        t = self.peek()
        if t.kind == "INT":
            self.advance()
            return n.IntLit(t.line, int(t.value))
        if t.kind in ("true", "false"):
            self.advance()
            return n.BoolLit(t.line, t.kind == "true")
        if t.kind == "NAME":
            self.advance()
            if self.at("("):
                self.advance()
                args = self.parse_expr_list(")")
                self.expect(")", "')' after arguments")
                return n.Call(t.line, t.value, args)
            return n.Name(t.line, t.value)
        if t.kind == "[":
            self.advance()
            elems = self.parse_expr_list("]")
            self.expect("]", "']' to close the array literal")
            return n.ArrayLit(t.line, elems)
        if t.kind == "(":
            self.advance()
            e = self.parse_expr()
            self.expect(")", "')'")
            return e
        found = t.value if t.value else t.kind.lower()
        raise CompileError(t.line, f"expected an expression, found {found!r}", t.col)


def parse(src: str) -> n.Program:
    return Parser(tokenize(src)).parse_program()
