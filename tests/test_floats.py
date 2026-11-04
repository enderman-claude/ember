"""Tests for f32, f64 and bigfloat: literals, type rules, code generation and runtime results."""
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember import floats                      # noqa: E402
from ember.driver import build, compile_to_asm  # noqa: E402
from ember.errors import CompileError          # noqa: E402
from ember.lexer import tokenize               # noqa: E402
from ember.parser import parse                 # noqa: E402

HAVE_TOOLS = bool(shutil.which("nasm") and shutil.which("cc"))
HAVE_ARM64 = bool(shutil.which("qemu-aarch64") and shutil.which("aarch64-linux-gnu-gcc"))
RUNTIME = ROOT / "ember" / "runtime"


def compile_error(src):
    try:
        compile_to_asm(src)
    except CompileError as e:
        return e
    raise AssertionError("expected a CompileError")


def body(stmts):
    return "def main():\n" + "".join(f"    {line}\n" for line in stmts.splitlines())


def run_program(src):
    with tempfile.TemporaryDirectory() as tmp:
        em = Path(tmp) / "prog.em"
        em.write_text(src)
        exe = build(em, Path(tmp) / "prog")
        return subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)


def f32_bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


class Literals(unittest.TestCase):
    def test_lexer_float_tokens(self):
        kinds = [(t.kind, t.value) for t in tokenize("x = 1.5\ny = 2big\nz = 3f32\nw = 1_000.000_1\n")
                 if t.kind not in ("NEWLINE", "EOF", "=", "NAME")]
        self.assertEqual(kinds, [("FLOAT", "1.5"), ("FLOATBIG", "2"), ("FLOAT32", "3"),
                                 ("FLOAT", "1000.0001")])

    def test_integers_stay_integers(self):
        self.assertEqual([t.kind for t in tokenize("1 2") if t.kind == "INT"], ["INT", "INT"])

    def test_suffix_must_end_the_number(self):
        # "1.5bigger" is not a bigfloat literal followed by a name: it is a syntax error.
        self.assertIn("found 'bigger'", compile_error(body("x = 1.5bigger")).msg)

    def test_literal_kinds(self):
        prog = parse("def main():\n    a = 1.5\n    b = 1.5f32\n    c = 1.5big\n")
        kinds = [s.expr.kind for s in prog.funcs[0].body]
        self.assertEqual(kinds, ["f64", "f32", "bigfloat"])

    def test_known_f32_values(self):
        self.assertEqual(floats.literal_bits("0.1", "f32"), f32_bits(0.1))
        self.assertEqual(floats.literal_bits("0.33333333333333333333", "f32"), 0x3EAAAAAB)
        # 16777217 is halfway between two f32 values; ties go to the even significand.
        self.assertEqual(floats.literal_bits("16777217", "f32"), 0x4B800000)

    def test_f64_literals_round_like_python(self):
        import random
        rng = random.Random(1)
        for _ in range(3000):
            text = f"{rng.randint(0, 10 ** rng.randint(1, 30))}.{rng.randint(0, 10 ** rng.randint(1, 25))}"
            want = struct.unpack("<Q", struct.pack("<d", float(text)))[0]
            self.assertEqual(floats.literal_bits(text, "f64"), want, text)

    def test_overflow_is_detected(self):
        self.assertIsNone(floats.literal_bits("1" + "0" * 39, "f32"))
        self.assertIsNotNone(floats.literal_bits("1" + "0" * 39, "f64"))


class TypeRules(unittest.TestCase):
    def test_no_implicit_conversion_between_numbers(self):
        self.assertIn("expected i64, found f64", compile_error(body("print(1 + 2.0)")).msg)
        self.assertIn("expected f64, found i64", compile_error(body("print(1.0 < 2)")).msg)
        self.assertIn("expected f32, found f64", compile_error(body("print(1.5f32 + 1.5)")).msg)
        self.assertIn("expected f64, found bigfloat", compile_error(body("print(1.5 * 2big)")).msg)

    def test_equality_needs_the_same_type(self):
        self.assertIn("cannot compare f64 with i64", compile_error(body("print(1.0 == 1)")).msg)

    def test_remainder_is_integer_only(self):
        self.assertIn("expected i64, found f64", compile_error(body("print(5.0 % 2.0)")).msg)

    def test_literal_too_big_for_f32(self):
        self.assertIn("does not fit in f32", compile_error(body("print(1" + "0" * 39 + ".0f32)")).msg)

    def test_negation_needs_a_number(self):
        self.assertIn("unary '-' needs a number, found bool", compile_error(body("print(-true)")).msg)

    def test_conversions_need_a_number(self):
        self.assertIn("cannot convert bool to f64", compile_error(body("print(f64(true))")).msg)
        self.assertIn("takes exactly 1 argument", compile_error(body("print(f64())")).msg)

    def test_extern_functions_take_c_types_only(self):
        src = "extern def c_scale(x: f64) -> f64\n\ndef main():\n    print(1)\n"
        self.assertIn("parameter 'x' has type f64", compile_error(src).msg)
        src = "extern def c_read() -> bigfloat\n\ndef main():\n    print(1)\n"
        self.assertIn("return type bigfloat", compile_error(src).msg)

    def test_float_names_are_reserved(self):
        self.assertIn("builtin", compile_error("def f64(x: i64) -> i64:\n    return x\n\ndef main():\n    print(1)\n").msg)

    def test_floats_in_functions(self):
        src = ("def half(x: f64) -> f64:\n    return x / 2.0\n\n"
               "def main():\n    print(half(3.0))\n")
        compile_to_asm(src)     # compiles

    def test_every_type_can_be_printed(self):
        for arg in ("1.5", "1.5f32", "1.5big", "1", "true"):
            with self.subTest(arg=arg):
                compile_to_asm(body(f"print({arg})"))


class CodeGeneration(unittest.TestCase):
    def test_f64_arithmetic_uses_sse(self):
        asm = compile_to_asm(body("x = 1.5 * 2.0\nprint(x / 4.0)"))
        self.assertIn("mulsd xmm0, xmm1", asm)
        self.assertIn("divsd xmm0, xmm1", asm)
        self.assertIn("call ember_print_f64", asm)

    def test_f32_arithmetic_uses_single_precision(self):
        asm = compile_to_asm(body("print(1.5f32 + 2.5f32)"))
        self.assertIn("addss xmm0, xmm1", asm)
        self.assertIn("call ember_print_f32", asm)

    def test_bigfloat_arithmetic_calls_the_runtime(self):
        asm = compile_to_asm(body("print(1big / 3big + 2big)"))
        self.assertIn("call ember_big_div", asm)
        self.assertIn("call ember_big_add", asm)
        self.assertIn("call ember_big_parse", asm)

    def test_conversions_call_the_runtime(self):
        asm = compile_to_asm(body("print(i64(f64(3) * 2.0))"))
        self.assertIn("call ember_convert", asm)

    def test_arm64_float_code(self):
        asm = compile_to_asm(body("print(1.5 * 2.0)\nprint(1.5 * 2.0 < 3.0)"), "linux-arm64")
        self.assertIn("fmul d0, d0, d1", asm)
        self.assertIn("fcmp d1, d0", asm)   # a < b is tested as b > a
        self.assertIn("bl ember_print_f64", asm)
        self.assertIn("bl ember_print_bool", asm)


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required")
class Runtime(unittest.TestCase):
    def test_example_outputs(self):
        for name in ("floats", "bigfloat"):
            with self.subTest(program=name):
                proc = run_program((ROOT / "examples" / f"{name}.em").read_text())
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout, (ROOT / "examples" / f"{name}.out").read_text())

    def test_bigfloat_division_by_zero_panics(self):
        proc = run_program(body("x = 1big / 0big\nprint(x)"))
        self.assertEqual(proc.returncode, 101)
        self.assertIn("division by zero", proc.stderr)

    def test_float_division_by_zero_is_infinity(self):
        proc = run_program(body("print(1.0 / 0.0)"))
        self.assertEqual(proc.stdout, "inf\n")

    def test_int_conversion_out_of_range_panics(self):
        proc = run_program(body("print(i64(1000000000000000000000000000000big))"))
        self.assertEqual(proc.returncode, 101)
        self.assertIn("does not fit in i64", proc.stderr)

    def test_nan_conversion_to_bigfloat_panics(self):
        proc = run_program(body("zero = 0.0\nprint(bigfloat(zero / zero))"))
        self.assertEqual(proc.returncode, 101)
        self.assertIn("NaN or infinity", proc.stderr)

    def test_bigfloat_values_are_exact(self):
        proc = run_program(body("x = 1big / 3big\nprint(x * 3big == 1big)\nprint(x * 3big)"))
        self.assertEqual(proc.stdout, "true\n1\n")

    def test_f32_arithmetic_rounds_to_single(self):
        proc = run_program(body("print(f32(1.0) / f32(3.0))"))
        self.assertEqual(proc.stdout, "0.33333334\n")


@unittest.skipUnless(HAVE_TOOLS and HAVE_ARM64, "needs nasm, cc, an AArch64 cross compiler and qemu-aarch64")
class CrossTarget(unittest.TestCase):
    CONSTANTS = ("def main():\n"
                 "    print(0x7FFFFFFFFFFFFFFF)\n"
                 "    print(-9223372036854775807 - 1)\n"
                 "    print(-5)\n"
                 "    print(0x123456789ABC)\n"
                 "    print(1.0 / 3.0)\n"
                 "    print(1.5f32 + 2.25f32)\n"
                 "    print(100big / 3big)\n")

    def test_x86_and_arm64_print_the_same(self):
        x86 = run_program(self.CONSTANTS)
        with tempfile.TemporaryDirectory() as tmp:
            em = Path(tmp) / "prog.em"
            em.write_text(self.CONSTANTS)
            exe = build(em, Path(tmp) / "prog64", target="linux-arm64")
            arm = subprocess.run(["qemu-aarch64", "-L", "/usr/aarch64-linux-gnu", str(exe)],
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(x86.stdout, arm.stdout)


class GeneratedCases(unittest.TestCase):
    def test_expected_results_are_current(self):
        """tests/num_cases.inc must match what tests/gen_num_cases.py produces."""
        sys.path.insert(0, str(ROOT / "tests"))
        import gen_num_cases
        committed = (ROOT / "tests" / "num_cases.inc").read_text()
        with tempfile.TemporaryDirectory() as tmp:
            saved = gen_num_cases.ROOT
            gen_num_cases.ROOT = Path(tmp)
            (Path(tmp) / "tests").mkdir()
            try:
                gen_num_cases.main()
                fresh = (Path(tmp) / "tests" / "num_cases.inc").read_text()
            finally:
                gen_num_cases.ROOT = saved
        self.assertEqual(committed, fresh, "run python3 tests/gen_num_cases.py")


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required")
class RuntimeUnits(unittest.TestCase):
    """Builds tests/num_test.c, which checks ember_num.h directly against known results."""

    def test_numeric_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "num_test"
            subprocess.run(["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                            f"-I{RUNTIME}", "-o", str(exe), str(ROOT / "tests" / "num_test.c")],
                           check=True, capture_output=True, text=True)
            proc = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("all numeric checks passed", proc.stdout)


HAVE_WINE = bool(shutil.which("wine") and shutil.which("nasm") and shutil.which("x86_64-w64-mingw32-gcc"))


@unittest.skipUnless(HAVE_WINE, "needs wine, nasm and the MinGW compiler")
class WindowsRun(unittest.TestCase):
    """Runs the float examples as Windows programs under wine.

    The driver links Windows programs as GUI applications, which have no console for print,
    so this test links the same code as a console program. Console output uses CRLF line
    endings on Windows (as integer printing always has); the comparison ignores them.
    """

    def build_console(self, em, exe):
        asm = compile_to_asm(em.read_text(), "windows")
        obj = exe.with_suffix(".obj")
        asm_file = exe.with_suffix(".asm")
        asm_file.write_text(asm)
        subprocess.run(["nasm", "-f", "win64", "-Werror", "-o", str(obj), str(asm_file)],
                       check=True, capture_output=True, text=True)
        subprocess.run(["x86_64-w64-mingw32-gcc", "-O1", "-static", "-o", str(exe),
                        str(RUNTIME / "ember_rt.c"), str(obj), "-luser32", "-lgdi32"],
                       check=True, capture_output=True, text=True)

    def test_examples_match_linux_output(self):
        import os
        env = dict(os.environ, WINEDEBUG="-all")
        for name in ("floats", "bigfloat"):
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                exe = Path(tmp) / f"{name}.exe"
                self.build_console(ROOT / "examples" / f"{name}.em", exe)
                proc = subprocess.run(["wine", str(exe)], capture_output=True, text=True,
                                      timeout=120, env=env)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.replace("\r\n", "\n"),
                                 (ROOT / "examples" / f"{name}.out").read_text())


@unittest.skipUnless(HAVE_TOOLS and shutil.which("x86_64-w64-mingw32-gcc"), "needs the MinGW compiler")
class StrictRuntimeBuilds(unittest.TestCase):
    def test_windows_runtime_compiles_without_warnings(self):
        subprocess.run(["x86_64-w64-mingw32-gcc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-c", str(RUNTIME / "ember_rt.c"), "-o", "/dev/null"],
                       check=True, capture_output=True, text=True)

    def test_shard_runtime_compiles_freestanding(self):
        subprocess.run(["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
                        "-fno-builtin", "-fno-stack-protector", "-fno-tree-loop-distribute-patterns",
                        "-c", str(RUNTIME / "ember_rt_shard.c"), "-o", "/dev/null"],
                       check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
