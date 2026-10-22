"""x86-64 code generator. Emits NASM syntax for ELF64 using the System V calling convention.

Design: every expression leaves its result in rax. Binary operators spill the left
operand to the stack. Each local variable gets a dedicated 8-byte slot in the frame.
"""
from . import nodes as n

ARG_REGS = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
BUILTIN_SYMBOLS = {"print": "ember_print_i64"}
CMP_SETCC = {"==": "sete", "!=": "setne", "<": "setl", "<=": "setle", ">": "setg", ">=": "setge"}


def align16(x: int) -> int:
    return (x + 15) & ~15


class CodeGen:
    def __init__(self):
        self.lines = []
        self.label_count = 0
        self.scopes = []
        self.nslots = 0
        self.ret_label = ""

    # -- output helpers -------------------------------------------------------
    def emit(self, text):
        self.lines.append("    " + text)

    def label(self, name):
        self.lines.append(f"{name}:")

    def new_label(self, hint):
        self.label_count += 1
        return f".L{hint}{self.label_count}"

    # -- program --------------------------------------------------------------
    def generate(self, prog: n.Program) -> str:
        self.lines = ["section .text"]
        for sym in sorted(set(BUILTIN_SYMBOLS.values())):
            self.lines.append(f"extern {sym}")
        for f in prog.funcs:
            self.gen_function(f)
        self.lines.append("section .note.GNU-stack noalloc noexec nowrite progbits")
        return "\n".join(self.lines) + "\n"

    def gen_function(self, f: n.FuncDef):
        symbol = f"em_{f.name}"
        self.ret_label = self.new_label("ret")
        self.scopes = [{}]
        self.nslots = 0

        # Generate the body first so the final frame size is known.
        saved = self.lines
        self.lines = []
        for p, reg in zip(f.params, ARG_REGS):
            self.emit(f"mov [rbp-{self.declare(p.name)}], {reg}")
        self.gen_block(f.body)
        body = self.lines
        self.lines = saved

        frame = align16(8 * self.nslots)
        self.lines.append(f"global {symbol}")
        self.label(symbol)
        self.emit("push rbp")
        self.emit("mov rbp, rsp")
        if frame:
            self.emit(f"sub rsp, {frame}")
        for k in range(1, self.nslots + 1):          # zero every slot for determinism
            self.emit(f"mov qword [rbp-{8 * k}], 0")
        self.lines.extend(body)
        self.label(self.ret_label)
        self.emit("mov rsp, rbp")
        self.emit("pop rbp")
        self.emit("ret")

    # -- scopes ---------------------------------------------------------------
    def declare(self, name) -> int:
        self.nslots += 1
        self.scopes[-1][name] = 8 * self.nslots
        return 8 * self.nslots

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise AssertionError(f"codegen: unresolved name {name!r} (checker should have caught this)")

    def gen_block(self, stmts):
        self.scopes.append({})
        for s in stmts:
            self.gen_stmt(s)
        self.scopes.pop()

    # -- statements -----------------------------------------------------------
    def gen_stmt(self, s):
        if isinstance(s, n.Let):
            self.gen_expr(s.expr)
            self.emit(f"mov [rbp-{self.declare(s.name)}], rax")

        elif isinstance(s, n.Assign):
            self.gen_expr(s.expr)
            found = None
            for scope in reversed(self.scopes):
                if s.name in scope:
                    found = scope[s.name]
                    break
            if found is None:
                found = self.declare(s.name)
            self.emit(f"mov [rbp-{found}], rax")

        elif isinstance(s, n.Return):
            if s.value is not None:
                self.gen_expr(s.value)
            self.emit(f"jmp {self.ret_label}")

        elif isinstance(s, n.If):
            end = self.new_label("endif")
            for cond, body in s.branches:
                nxt = self.new_label("next")
                self.gen_expr(cond)
                self.emit("cmp rax, 0")
                self.emit(f"je {nxt}")
                self.gen_block(body)
                self.emit(f"jmp {end}")
                self.label(nxt)
            if s.else_body is not None:
                self.gen_block(s.else_body)
            self.label(end)

        elif isinstance(s, n.While):
            top = self.new_label("while")
            end = self.new_label("endwhile")
            self.label(top)
            self.gen_expr(s.cond)
            self.emit("cmp rax, 0")
            self.emit(f"je {end}")
            self.gen_block(s.body)
            self.emit(f"jmp {top}")
            self.label(end)

        elif isinstance(s, n.ExprStmt):
            self.gen_expr(s.expr)

    # -- expressions (result in rax) -------------------------------------------
    def gen_expr(self, e):
        if isinstance(e, n.IntLit):
            self.emit(f"mov rax, {e.value}")

        elif isinstance(e, n.BoolLit):
            self.emit(f"mov rax, {1 if e.value else 0}")

        elif isinstance(e, n.Name):
            self.emit(f"mov rax, [rbp-{self.lookup(e.name)}]")

        elif isinstance(e, n.Unary):
            self.gen_expr(e.operand)
            if e.op == "-":
                self.emit("neg rax")
            else:
                self.emit("xor rax, 1")          # bools are always 0 or 1

        elif isinstance(e, n.Binary):
            if e.op in ("and", "or"):
                # short-circuit: skip the right side when the left one decides the result
                end = self.new_label("sc")
                self.gen_expr(e.left)
                self.emit("cmp rax, 0")
                self.emit(f"{'je' if e.op == 'and' else 'jne'} {end}")
                self.gen_expr(e.right)
                self.label(end)
            else:
                self.gen_expr(e.left)
                self.emit("push rax")
                self.gen_expr(e.right)
                self.emit("mov rcx, rax")
                self.emit("pop rax")
                if e.op == "+":
                    self.emit("add rax, rcx")
                elif e.op == "-":
                    self.emit("sub rax, rcx")
                elif e.op == "*":
                    self.emit("imul rax, rcx")
                elif e.op == "/":
                    self.emit("cqo")
                    self.emit("idiv rcx")
                elif e.op == "%":
                    self.emit("cqo")
                    self.emit("idiv rcx")
                    self.emit("mov rax, rdx")
                else:
                    self.emit("cmp rax, rcx")
                    self.emit(f"{CMP_SETCC[e.op]} al")
                    self.emit("movzx rax, al")

        elif isinstance(e, n.Call):
            for arg in e.args:
                self.gen_expr(arg)
                self.emit("push rax")
            for reg in reversed(ARG_REGS[:len(e.args)]):
                self.emit(f"pop {reg}")
            symbol = BUILTIN_SYMBOLS.get(e.name, f"em_{e.name}")
            # Align rsp to 16 bytes for the call, whatever the expression depth.
            # rbx is callee-saved, so it is restored afterwards.
            self.emit("push rbx")
            self.emit("mov rbx, rsp")
            self.emit("and rsp, -16")
            self.emit(f"call {symbol}")
            self.emit("mov rsp, rbx")
            self.emit("pop rbx")

        else:
            raise AssertionError(f"codegen: unknown expression {e!r}")


def generate(prog: n.Program) -> str:
    return CodeGen().generate(prog)
