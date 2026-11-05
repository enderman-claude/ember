"""Tests for the math builtins: sqrt, sin, cos, tan, atan, atan2, exp, ln, floor, ceil, abs."""
import math
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ember.driver import SHARD_RUNTIME, build, compile_to_asm  # noqa: E402
from ember.errors import CompileError                            # noqa: E402

HAVE_CC = bool(shutil.which("cc"))
HAVE_TOOLS = bool(shutil.which("nasm") and shutil.which("cc"))
RUNTIME = ROOT / "ember" / "runtime"
MATH_FUNCS = ["sqrt", "sin", "cos", "tan", "atan", "atan2", "exp", "ln", "floor", "ceil", "abs"]


def body(stmts):
    return "def main():\n" + "".join(f"    {line}\n" for line in stmts.splitlines())


def compile_error(src):
    try:
        compile_to_asm(src)
    except CompileError as e:
        return e
    raise AssertionError("expected a CompileError")


def run_program(src):
    with tempfile.TemporaryDirectory() as tmp:
        em = Path(tmp) / "prog.em"
        em.write_text(src)
        exe = build(em, Path(tmp) / "prog")
        return subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)


def ulps(a, b):
    def key(x):
        n = struct.unpack("<q", struct.pack("<d", x))[0]
        return n if n >= 0 else -(1 << 63) - n
    return abs(key(a) - key(b))


class Checking(unittest.TestCase):
    def test_i64_is_rejected_with_a_hint(self):
        msg = compile_error(body("print(sqrt(4))")).msg
        self.assertIn("takes f32 or f64, found i64", msg)
        self.assertIn("f64(x)", msg)

    def test_bigfloat_is_rejected(self):
        self.assertIn("bigfloat is exact", compile_error(body("print(sqrt(2.0big))")).msg)

    def test_argument_count(self):
        self.assertIn("takes 1 argument(s), got 2", compile_error(body("print(sin(1.0, 2.0))")).msg)
        self.assertIn("takes 2 argument(s), got 1", compile_error(body("print(atan2(1.0))")).msg)

    def test_atan2_needs_matching_types(self):
        self.assertIn("same type", compile_error(body("print(atan2(1.0, 1.0f32))")).msg)

    def test_result_type_follows_the_argument(self):
        # sqrt of an f64 is an f64, so it cannot be returned from a function declared -> f32
        err = compile_error("def f() -> f32:\n    return sqrt(2.0)\n\ndef main():\n    print(1)\n")
        self.assertIn("f32", err.msg)
        compile_to_asm("def f() -> f32:\n    return sqrt(2.0f32)\n\ndef main():\n    print(1)\n")

    def test_names_are_reserved_for_functions_only(self):
        self.assertIn("builtin", compile_error("def sqrt(x: f64) -> f64:\n    return x\n"
                                               "\ndef main():\n    print(1)\n").msg)
        compile_to_asm(body("exp = 3\nabs = exp + 1\nprint(abs)"))  # variables are fine

    def test_every_backend_calls_the_runtime_symbol(self):
        src = body("print(atan2(1.0, 2.0))\nprint(sqrt(2.0f32))")
        for target in ("linux", "windows", "linux-arm64", "windows-arm64"):
            asm = compile_to_asm(src, target)
            self.assertIn("ember_atan2_f64", asm, target)
            self.assertIn("ember_sqrt_f32", asm, target)

    def test_x86_declares_every_symbol_it_could_use(self):
        from ember.codegen import RUNTIME_SYMBOLS
        for name in MATH_FUNCS:
            for t in ("f32", "f64"):
                self.assertIn(f"ember_{name}_{t}", RUNTIME_SYMBOLS)


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required")
class Running(unittest.TestCase):
    def test_exact_results(self):
        r = run_program(body("""print(sqrt(16.0))
print(sqrt(2.25))
print(floor(-1.5))
print(ceil(-1.5))
print(floor(2.0))
print(abs(-3.25))
print(abs(3.25))
print(sin(0.0))
print(cos(0.0))
print(exp(0.0))
print(ln(1.0))
print(atan(0.0))"""))
        self.assertEqual(r.stdout.split(), ["4.0", "1.5", "-2.0", "-1.0", "2.0", "3.25", "3.25",
                                            "0.0", "1.0", "1.0", "0.0", "0.0"])

    def test_sqrt_is_correctly_rounded(self):
        # Python's math.sqrt is correctly rounded, so the digits must match exactly.
        # Ember has no exponent notation, so extreme magnitudes are covered by math_test.c.
        xs = ["2.0", "3.0", "5.0", "10.0", "0.1", "0.000001", "123456.789", "99999999999.5",
              "0.3333333333333333"]
        r = run_program(body("\n".join(f"print(sqrt({x}))" for x in xs)))
        self.assertEqual(r.stdout.split(), [repr(math.sqrt(float(x))) for x in xs])

    def test_close_to_python_for_the_rest(self):
        cases = [("sin", "sin(1.0)", math.sin(1.0)), ("cos", "cos(1.0)", math.cos(1.0)),
                 ("tan", "tan(1.0)", math.tan(1.0)), ("atan", "atan(0.5)", math.atan(0.5)),
                 ("atan2", "atan2(1.0, 2.0)", math.atan2(1.0, 2.0)),
                 ("atan2", "atan2(-1.0, -2.0)", math.atan2(-1.0, -2.0)),
                 ("exp", "exp(2.5)", math.exp(2.5)), ("exp", "exp(-20.0)", math.exp(-20.0)),
                 ("ln", "ln(10.0)", math.log(10.0)), ("ln", "ln(0.001)", math.log(0.001)),
                 ("sin", "sin(1000.0)", math.sin(1000.0)), ("cos", "cos(-3.0)", math.cos(-3.0))]
        r = run_program(body("\n".join(f"print({e})" for _, e, _ in cases)))
        got = r.stdout.split()
        self.assertEqual(len(got), len(cases), r.stdout + r.stderr)
        for (name, expr, want), text in zip(cases, got):
            self.assertLessEqual(ulps(float(text), want), 4, f"{expr}: {text} vs {want!r}")

    def test_special_values_follow_ieee(self):
        r = run_program(body("""zero = 0.0
one = 1.0
print(sqrt(zero - one))
print(ln(zero))
print(ln(zero - one))
print(exp(1000.0))
print(exp(zero - 1000.0))
print(atan2(zero, zero - one))
print(sqrt(one / zero))
print(sin(one / zero))
print(sin(10000000.0))"""))
        self.assertEqual(r.stdout.split(),
                         ["nan", "-inf", "nan", "inf", "0.0", "3.141592653589793", "inf", "nan", "nan"])

    def test_f32_is_computed_in_double_and_rounded_once(self):
        r = run_program(body("print(sqrt(2.0f32))\nprint(sin(1.0f32))\nprint(floor(-0.5f32))"))
        f = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]   # round to f32
        got = r.stdout.split()
        # An f32 prints as its shortest decimal, so read it back as an f32 to compare.
        self.assertEqual(f(float(got[0])), f(math.sqrt(f(2.0))))
        self.assertEqual(f(float(got[1])), f(math.sin(f(1.0))))
        self.assertEqual(got[2], "-1.0")

    def test_builtins_work_inside_functions_and_loops(self):
        r = run_program("""def hyp(a: f64, b: f64) -> f64:
    return sqrt(a * a + b * b)

def main():
    mut total = 0.0
    for i in range(1, 4):
        total = total + hyp(f64(i), 4.0)
    print(total > 12.0)
    print(floor(hyp(3.0, 4.0)))
""")
        self.assertEqual(r.stdout.split(), ["true", "5.0"])


@unittest.skipUnless(HAVE_TOOLS and platform.machine() in ("x86_64", "AMD64"),
                     "needs nasm, cc and an x86-64 host")
class Freestanding(unittest.TestCase):
    def test_shard_runtime_links_without_libc_or_libm(self):
        src = body("print(sqrt(2.0))\nprint(sin(1.0))\nprint(atan2(1.0, 2.0))\nprint(exp(1.5))"
                   "\nprint(ln(3.0))\nprint(floor(-2.5))\nprint(tan(0.5f32))")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "p.asm").write_text(compile_to_asm(src, "shard"))
            subprocess.run(["nasm", "-f", "elf64", "-Werror", "-o", str(tmp / "p.o"),
                            str(tmp / "p.asm")], check=True)
            link = subprocess.run(
                ["cc", "-O1", "-static-pie", "-nostdlib", "-ffreestanding", "-fno-builtin",
                 "-fno-stack-protector", "-fno-tree-loop-distribute-patterns",
                 "-o", str(tmp / "p.elf"), str(SHARD_RUNTIME), str(tmp / "p.o")],
                capture_output=True, text=True)
            self.assertEqual(link.returncode, 0, link.stderr)
            undefined = subprocess.run(["nm", "-u", str(tmp / "p.elf")],
                                       capture_output=True, text=True).stdout.strip()
            self.assertEqual(undefined, "", "the shard image must not need libc, libm or libgcc")
            shard = subprocess.run([str(tmp / "p.elf")], capture_output=True, text=True, timeout=20)
        libc = run_program(src)
        self.assertEqual(shard.stdout, libc.stdout)


@unittest.skipUnless(HAVE_CC, "cc is required")
class Runtime(unittest.TestCase):
    def test_constants_match_the_generator(self):
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "gen_math_consts.py"), "--check"])
        self.assertEqual(r.returncode, 0, "run python3 tests/gen_math_consts.py")

    def test_against_libm(self):
        """tests/math_test.c compares every function with libm over millions of inputs."""
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "math_test"
            subprocess.run(["cc", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                            f"-I{RUNTIME}", "-o", str(exe), str(ROOT / "tests" / "math_test.c"),
                            "-lm"], check=True)
            r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=240)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn("all math checks passed", r.stdout)

    @unittest.skipUnless(platform.machine() in ("x86_64", "AMD64"), "FMA experiment is x86-64")
    def test_fused_multiply_add_cannot_change_results(self):
        """With FMA available, results must not depend on whether the compiler may fuse.

        The control build (pragma disabled) must differ, otherwise the test proves nothing."""
        probe = subprocess.run(["cc", "-mfma", "-x", "c", "-", "-o", "/dev/null"],
                               input="int main(void){return 0;}", capture_output=True, text=True)
        if probe.returncode != 0:
            self.skipTest("cc does not accept -mfma")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "checksum.c"
            src.write_text(CHECKSUM_C)

            def checksum(*flags):
                exe = tmp / ("c" + str(abs(hash(flags))))
                subprocess.run(["cc", "-std=gnu11", "-O2", "-w", f"-I{RUNTIME}", *flags,
                                "-o", str(exe), str(src)], check=True)
                return subprocess.run([str(exe)], capture_output=True, text=True).stdout.strip()

            plain = checksum()
            self.assertEqual(checksum("-mfma"), plain, "the pragma must stop FMA changing results")
            control = checksum("-mfma", "-DEM_KEEP_FP_CONTRACT", "-ffp-contract=fast")
            if control == plain:
                self.skipTest("this compiler did not fuse in the control build")


CHECKSUM_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include "ember_num.h"
#include "ember_math.h"
void *ember_num_alloc(size_t b) { return malloc(b ? b : 1); }
void ember_num_free(void *p) { free(p); }
void ember_panic(int64_t c) { exit(101); }
static uint64_t s = 0x1234567887654321ULL;
static uint64_t rnd(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s; }
static double u(void) { return (double)(rnd() >> 11) / 9007199254740992.0; }
int main(void) {
    uint64_t h = 1469598103934665603ULL;
#define MIX(v) do { h ^= f64_to_bits(v); h *= 1099511628211ULL; } while (0)
    for (int i = 0; i < 100000; i++) {
        double x = -50.0 + 100.0 * u(), p = 0.001 + 1000.0 * u(), w = -700.0 + 1400.0 * u();
        double t = -1.6e6 + 3.2e6 * u();
        MIX(em_sin(x)); MIX(em_cos(x)); MIX(em_tan(x)); MIX(em_sin(t)); MIX(em_cos(t));
        MIX(em_tan(t)); MIX(em_atan(x)); MIX(em_atan2(x, w)); MIX(em_exp(w)); MIX(em_ln(p));
        MIX(em_sqrt(p));
    }
    printf("%016llx\n", (unsigned long long)h);
    return 0;
}
"""

if __name__ == "__main__":
    unittest.main()
