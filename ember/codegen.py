"""x86-64 code generator. Emits NASM syntax for ELF64 using the System V calling convention.

Design: every expression leaves its result in rax. Binary operators spill the left
operand to the stack. Each local (and each compiler temporary) gets a dedicated
8-byte frame slot. Calls into the runtime go through emit_call, which keeps rsp
16-byte aligned regardless of how deep the expression stack is.
"""
from . import nodes as n

SYSV_ARG_REGS = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]   # Linux (System V)
WIN_ARG_REGS = ["rcx", "rdx", "r8", "r9"]                   # Windows x64
CMP_SETCC = {"==": "sete", "!=": "setne", "<": "setl", "<=": "setle", ">": "setg", ">=": "setge"}
RUNTIME_SYMBOLS = [
    "ember_print_i64", "ember_print_bool", "ember_alloc", "ember_free", "ember_len",
    "ember_load", "ember_store", "ember_read_int", "ember_input_ended", "ember_put_byte",
    "ember_panic",
]
WINDOW_SYMBOLS = ["ember_window_open", "ember_window_present", "ember_window_closed"]


def align16(x: int) -> int:
    return (x + 15) & ~15


class CodeGen:
    def __init__(self):
        self.lines = []
        self.label_count = 0
        self.scopes = []
        self.nslots = 0
        self.ret_label = ""
        self.loops = []          # stack of (continue_label, break_label)
        self.target = "linux"
        self.arg_regs = SYSV_ARG_REGS

    # -- output helpers -------------------------------------------------------
    def emit(self, text):
        self.lines.append("    " + text)

    def label(self, name):
        self.lines.append(f"{name}:")

    def new_label(self, hint):
        self.label_count += 1
        return f".L{hint}{self.label_count}"

    # -- program --------------------------------------------------------------
    def generate(self, prog: n.Program, target: str = "linux") -> str:
        self.target = target
        self.arg_regs = WIN_ARG_REGS if target == "windows" else SYSV_ARG_REGS
        self.lines = ["section .text"]
        symbols = RUNTIME_SYMBOLS + (WINDOW_SYMBOLS if target == "windows" else [])
        for sym in symbols:
            self.lines.append(f"extern {sym}")
        for f in prog.funcs:
            if f.body is None:                   # extern: declared above by its C name
                self.lines.append(f"extern {f.name}")
            else:
                self.gen_function(f)
        if target == "linux":
            self.lines.append("section .note.GNU-stack noalloc noexec nowrite progbits")
        return "\n".join(self.lines) + "\n"

    def gen_function(self, f: n.FuncDef):
        self.ret_label = self.new_label("ret")
        self.scopes = [{}]
        self.nslots = 0
        self.loops = []

        # Generate the body first so the final frame size is known.
        saved = self.lines
        self.lines = []
        for p, reg in zip(f.params, self.arg_regs):
            self.emit(f"mov [rbp-{self.declare(p.name)}], {reg}")
        self.gen_block(f.body)
        body = self.lines
        self.lines = saved

        frame = align16(8 * self.nslots)
        self.lines.append(f"global em_{f.name}")
        self.label(f"em_{f.name}")
        self.emit("push rbp")
        self.emit("mov rbp, rsp")
        if frame:
            self.emit(f"sub rsp, {frame}")
        for k in range(1, self.nslots + 1):        # zero every slot for determinism
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

    def find(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def lookup(self, name):
        off = self.find(name)
        if off is None:
            raise AssertionError(f"codegen: unresolved name {name!r} (the checker should have caught this)")
        return off

    def gen_block(self, stmts):
        self.scopes.append({})
        for s in stmts:
            self.gen_stmt(s)
        self.scopes.pop()

    # -- calls ----------------------------------------------------------------
    def emit_call(self, symbol):
        """Call with rsp aligned to 16 bytes. rbx (callee-saved) is restored afterwards."""
        self.emit("push rbx")
        self.emit("mov rbx, rsp")
        self.emit("and rsp, -16")
        self.emit("sub rsp, 32")                 # shadow space required by the Windows ABI
        self.emit(f"call {symbol}")
        self.emit("mov rsp, rbx")
        self.emit("pop rbx")

    def gen_call(self, args, symbol):
        for a in args:
            self.gen_expr(a)
            self.emit("push rax")
        for reg in reversed(self.arg_regs[:len(args)]):
            self.emit(f"pop {reg}")
        self.emit_call(symbol)

    # -- statements -----------------------------------------------------------
    def gen_stmt(self, s):
        if isinstance(s, n.Let):
            self.gen_expr(s.expr)
            self.emit(f"mov [rbp-{self.declare(s.name)}], rax")

        elif isinstance(s, n.Assign):
            self.gen_expr(s.expr)
            off = self.find(s.name)
            if off is None:
                off = self.declare(s.name)
            self.emit(f"mov [rbp-{off}], rax")

        elif isinstance(s, n.IndexAssign):
            self.gen_call([s.target, s.index, s.value], "ember_store")

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
            self.loops.append((top, end))
            self.gen_block(s.body)
            self.loops.pop()
            self.emit(f"jmp {top}")
            self.label(end)

        elif isinstance(s, n.For):
            # Bounds are evaluated once, in the enclosing scope, into hidden slots.
            start_slot = self.declare(self.new_label("start"))
            stop_slot = self.declare(self.new_label("stop"))
            self.gen_expr(s.start)
            self.emit(f"mov [rbp-{start_slot}], rax")
            self.gen_expr(s.stop)
            self.emit(f"mov [rbp-{stop_slot}], rax")

            self.scopes.append({})
            var = self.declare(s.name)
            self.emit(f"mov rax, [rbp-{start_slot}]")
            self.emit(f"mov [rbp-{var}], rax")
            top = self.new_label("for")
            cont = self.new_label("forcont")
            end = self.new_label("endfor")
            self.label(top)
            self.emit(f"mov rax, [rbp-{var}]")
            self.emit(f"cmp rax, [rbp-{stop_slot}]")
            self.emit(f"jge {end}")
            self.loops.append((cont, end))
            self.gen_block(s.body)
            self.loops.pop()
            self.label(cont)
            self.emit(f"add qword [rbp-{var}], 1")
            self.emit(f"jmp {top}")
            self.label(end)
            self.scopes.pop()

        elif isinstance(s, n.Break):
            self.emit(f"jmp {self.loops[-1][1]}")

        elif isinstance(s, n.Continue):
            self.emit(f"jmp {self.loops[-1][0]}")

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
                # short-circuit: the right side is skipped when the left decides the result
                end = self.new_label("sc")
                self.gen_expr(e.left)
                self.emit("cmp rax, 0")
                self.emit(f"{'je' if e.op == 'and' else 'jne'} {end}")
                self.gen_expr(e.right)
                self.label(end)
            else:
                self.gen_binary(e)

        elif isinstance(e, n.Call):
            self.gen_call(e.args, e.symbol)

        elif isinstance(e, n.Index):
            self.gen_call([e.target, e.index], "ember_load")

        elif isinstance(e, n.ArrayLit):
            handle = self.declare(self.new_label("arr"))
            self.gen_call([n.IntLit(e.line, len(e.elems))], "ember_alloc")
            self.emit(f"mov [rbp-{handle}], rax")
            for i, el in enumerate(e.elems):
                self.gen_expr(el)
                a0, a1, a2 = self.arg_regs[:3]
                self.emit(f"mov {a2}, rax")
                self.emit(f"mov {a0}, [rbp-{handle}]")
                self.emit(f"mov {a1}, {i}")
                self.emit_call("ember_store")
            self.emit(f"mov rax, [rbp-{handle}]")

        else:
            raise AssertionError(f"codegen: unknown expression {e!r}")

    def gen_binary(self, e):
        self.gen_expr(e.left)
        self.emit("push rax")
        self.gen_expr(e.right)
        self.emit("mov rcx, rax")
        self.emit("pop rax")
        op = e.op
        if op == "+":
            self.emit("add rax, rcx")
        elif op == "-":
            self.emit("sub rax, rcx")
        elif op == "*":
            self.emit("imul rax, rcx")
        elif op in ("/", "%"):
            self.gen_divide(is_mod=(op == "%"))
        else:
            self.emit("cmp rax, rcx")
            self.emit(f"{CMP_SETCC[op]} al")
            self.emit("movzx rax, al")

    def gen_divide(self, is_mod: bool):
        """rax / rcx (or rax % rcx). Panics on division by zero; wraps INT_MIN / -1 like two's complement."""
        ok = self.new_label("divok")
        normal = self.new_label("divnorm")
        done = self.new_label("divdone")
        self.emit("test rcx, rcx")
        self.emit(f"jnz {ok}")
        self.emit(f"mov {self.arg_regs[0]}, 1")  # panic code 1: division by zero
        self.emit_call("ember_panic")
        self.label(ok)
        self.emit("cmp rcx, -1")
        self.emit(f"jne {normal}")               # idiv traps on INT_MIN / -1, so special-case it
        self.emit("xor eax, eax" if is_mod else "neg rax")
        self.emit(f"jmp {done}")
        self.label(normal)
        self.emit("cqo")
        self.emit("idiv rcx")
        if is_mod:
            self.emit("mov rax, rdx")
        self.label(done)


def generate(prog: n.Program, target: str = "linux") -> str:
    return CodeGen().generate(prog, target)
