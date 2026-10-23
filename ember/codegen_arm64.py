"""AArch64 (ARM64) code generator for Linux. Emits GNU assembler syntax using the AAPCS64 calling convention.

Same design as the x86-64 generator in codegen.py: every expression leaves its result in x0.
Binary operators spill the left operand to the stack, 16 bytes at a time, which keeps sp
16-byte aligned at every call site without any extra bookkeeping. Each local (and each
compiler temporary) gets a dedicated 8-byte frame slot addressed from the frame pointer x29.

Scratch registers: x9 is free for temporaries, x16 (IP0) is used to reach frame slots whose
offset is too large for the single-instruction addressing form.
"""
from . import nodes as n

ARG_REGS = ["x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7"]
CMP_COND = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}
UNSCALED_LIMIT = 256       # ldur/stur reach -256..255 from the frame pointer


def align16(x: int) -> int:
    return (x + 15) & ~15


class CodeGenArm64:
    def __init__(self):
        self.lines = []
        self.label_count = 0
        self.scopes = []
        self.nslots = 0
        self.ret_label = ""
        self.loops = []          # stack of (continue_label, break_label)

    # -- output helpers -------------------------------------------------------
    def emit(self, text):
        self.lines.append("    " + text)

    def label(self, name):
        self.lines.append(f"{name}:")

    def new_label(self, hint):
        self.label_count += 1
        return f".L{hint}{self.label_count}"

    # -- frame slots ----------------------------------------------------------
    # Slot k lives at [x29 - 8k]. Offsets beyond the unscaled range go through x16.
    def load_slot(self, reg, off):
        if off <= UNSCALED_LIMIT:
            self.emit(f"ldur {reg}, [x29, #-{off}]")
        else:
            self.emit(f"mov x16, #{off}")
            self.emit("sub x16, x29, x16")
            self.emit(f"ldr {reg}, [x16]")

    def store_slot(self, reg, off):
        if off <= UNSCALED_LIMIT:
            self.emit(f"stur {reg}, [x29, #-{off}]")
        else:
            self.emit(f"mov x16, #{off}")
            self.emit("sub x16, x29, x16")
            self.emit(f"str {reg}, [x16]")

    def push(self, reg):
        self.emit(f"str {reg}, [sp, #-16]!")

    def pop(self, reg):
        self.emit(f"ldr {reg}, [sp], #16")

    # -- program --------------------------------------------------------------
    def generate(self, prog: n.Program) -> str:
        self.lines = [".text"]
        for f in prog.funcs:
            if f.body is not None:               # extern functions are resolved by the linker
                self.gen_function(f)
        self.lines.append('.section .note.GNU-stack,"",@progbits')
        return "\n".join(self.lines) + "\n"

    def gen_function(self, f: n.FuncDef):
        self.ret_label = self.new_label("ret")
        self.scopes = [{}]
        self.nslots = 0
        self.loops = []

        # Generate the body first so the final frame size is known.
        saved = self.lines
        self.lines = []
        for p, reg in zip(f.params, ARG_REGS):
            self.store_slot(reg, self.declare(p.name))
        self.gen_block(f.body)
        body = self.lines
        self.lines = saved

        frame = align16(8 * self.nslots)
        self.emit_raw_label_block(f.name)
        self.emit("stp x29, x30, [sp, #-16]!")
        self.emit("mov x29, sp")
        if frame:
            self.emit(f"mov x16, #{frame}")
            self.emit("sub sp, sp, x16")
        for k in range(1, self.nslots + 1):      # zero every slot for determinism
            self.store_slot("xzr", 8 * k)
        self.lines.extend(body)
        self.label(self.ret_label)
        self.emit("mov sp, x29")
        self.emit("ldp x29, x30, [sp], #16")
        self.emit("ret")

    def emit_raw_label_block(self, name):
        self.lines.append("    .p2align 2")
        self.lines.append(f"    .globl em_{name}")
        self.label(f"em_{name}")

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
    def gen_call(self, args, symbol):
        for a in args:
            self.gen_expr(a)
            self.push("x0")
        for reg in reversed(ARG_REGS[:len(args)]):
            self.pop(reg)
        self.emit(f"bl {symbol}")

    # -- statements -----------------------------------------------------------
    def gen_stmt(self, s):
        if isinstance(s, n.Let):
            self.gen_expr(s.expr)
            self.store_slot("x0", self.declare(s.name))

        elif isinstance(s, n.Assign):
            self.gen_expr(s.expr)
            off = self.find(s.name)
            if off is None:
                off = self.declare(s.name)
            self.store_slot("x0", off)

        elif isinstance(s, n.IndexAssign):
            self.gen_call([s.target, s.index, s.value], "ember_store")

        elif isinstance(s, n.Return):
            if s.value is not None:
                self.gen_expr(s.value)
            self.emit(f"b {self.ret_label}")

        elif isinstance(s, n.If):
            end = self.new_label("endif")
            for cond, body in s.branches:
                nxt = self.new_label("next")
                self.gen_expr(cond)
                self.emit(f"cbz x0, {nxt}")
                self.gen_block(body)
                self.emit(f"b {end}")
                self.label(nxt)
            if s.else_body is not None:
                self.gen_block(s.else_body)
            self.label(end)

        elif isinstance(s, n.While):
            top = self.new_label("while")
            end = self.new_label("endwhile")
            self.label(top)
            self.gen_expr(s.cond)
            self.emit(f"cbz x0, {end}")
            self.loops.append((top, end))
            self.gen_block(s.body)
            self.loops.pop()
            self.emit(f"b {top}")
            self.label(end)

        elif isinstance(s, n.For):
            # Bounds are evaluated once, in the enclosing scope, into hidden slots.
            start_slot = self.declare(self.new_label("start"))
            stop_slot = self.declare(self.new_label("stop"))
            self.gen_expr(s.start)
            self.store_slot("x0", start_slot)
            self.gen_expr(s.stop)
            self.store_slot("x0", stop_slot)

            self.scopes.append({})
            var = self.declare(s.name)
            self.load_slot("x0", start_slot)
            self.store_slot("x0", var)
            top = self.new_label("for")
            cont = self.new_label("forcont")
            end = self.new_label("endfor")
            self.label(top)
            self.load_slot("x0", var)
            self.load_slot("x1", stop_slot)
            self.emit("cmp x0, x1")
            self.emit(f"b.ge {end}")
            self.loops.append((cont, end))
            self.gen_block(s.body)
            self.loops.pop()
            self.label(cont)
            self.load_slot("x0", var)
            self.emit("add x0, x0, #1")
            self.store_slot("x0", var)
            self.emit(f"b {top}")
            self.label(end)
            self.scopes.pop()

        elif isinstance(s, n.Break):
            self.emit(f"b {self.loops[-1][1]}")

        elif isinstance(s, n.Continue):
            self.emit(f"b {self.loops[-1][0]}")

        elif isinstance(s, n.ExprStmt):
            self.gen_expr(s.expr)

    # -- expressions (result in x0) --------------------------------------------
    def gen_expr(self, e):
        if isinstance(e, n.IntLit):
            self.emit(f"mov x0, #{e.value}")

        elif isinstance(e, n.BoolLit):
            self.emit(f"mov x0, #{1 if e.value else 0}")

        elif isinstance(e, n.Name):
            self.load_slot("x0", self.lookup(e.name))

        elif isinstance(e, n.Unary):
            self.gen_expr(e.operand)
            if e.op == "-":
                self.emit("neg x0, x0")
            else:
                self.emit("eor x0, x0, #1")      # bools are always 0 or 1

        elif isinstance(e, n.Binary):
            if e.op in ("and", "or"):
                # short-circuit: the right side is skipped when the left decides the result
                end = self.new_label("sc")
                self.gen_expr(e.left)
                self.emit(f"{'cbz' if e.op == 'and' else 'cbnz'} x0, {end}")
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
            self.store_slot("x0", handle)
            for i, el in enumerate(e.elems):
                self.gen_expr(el)
                self.emit("mov x2, x0")
                self.load_slot("x0", handle)
                self.emit(f"mov x1, #{i}")
                self.emit("bl ember_store")
            self.load_slot("x0", handle)

        else:
            raise AssertionError(f"codegen: unknown expression {e!r}")

    def gen_binary(self, e):
        self.gen_expr(e.left)
        self.push("x0")
        self.gen_expr(e.right)
        self.emit("mov x1, x0")
        self.pop("x0")
        op = e.op
        if op == "+":
            self.emit("add x0, x0, x1")
        elif op == "-":
            self.emit("sub x0, x0, x1")
        elif op == "*":
            self.emit("mul x0, x0, x1")
        elif op in ("/", "%"):
            self.gen_divide(is_mod=(op == "%"))
        else:
            self.emit("cmp x0, x1")
            self.emit(f"cset x0, {CMP_COND[op]}")

    def gen_divide(self, is_mod: bool):
        """x0 / x1 (or x0 % x1). Panics on division by zero.

        sdiv truncates toward zero and does not trap on INT_MIN / -1 (it wraps to INT_MIN,
        as two's complement does), so no special case is needed here, unlike x86.
        """
        ok = self.new_label("divok")
        self.emit(f"cbnz x1, {ok}")
        self.emit("mov x0, #1")                  # panic code 1: division by zero
        self.emit("bl ember_panic")
        self.label(ok)
        self.emit("sdiv x2, x0, x1")
        if is_mod:
            self.emit("msub x0, x2, x1, x0")     # remainder = dividend - quotient * divisor
        else:
            self.emit("mov x0, x2")


def generate(prog: n.Program) -> str:
    return CodeGenArm64().generate(prog)
