"""AArch64 (linux-arm64) target tests.

Compile-level tests run everywhere. End-to-end tests build each example for AArch64 and run
it: natively on an ARM64 Linux host, or under qemu-user (qemu-aarch64 with the GNU sysroot)
elsewhere. They are skipped when neither is available.
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import arm64_compiler, build, compile_to_asm  # noqa: E402
from ember.errors import CompileError                           # noqa: E402

ARM_SYSROOT = Path("/usr/aarch64-linux-gnu")
NATIVE_ARM = platform.machine().lower() in ("aarch64", "arm64")
QEMU = shutil.which("qemu-aarch64")
CC = arm64_compiler()
HAVE_ARM_TOOLS = bool(shutil.which(CC))
CAN_RUN_ARM = HAVE_ARM_TOOLS and (NATIVE_ARM or (QEMU is not None and ARM_SYSROOT.is_dir()))
EXPECTED_EXIT = {"bounds_demo": 101}
EXAMPLES = sorted((ROOT / "examples").glob("*.em"))


def run_command(exe, stdin=""):
    """Run an AArch64 executable, through qemu-user when the host is not ARM64."""
    cmd = [str(exe)] if NATIVE_ARM else [QEMU, "-L", str(ARM_SYSROOT), str(exe)]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60)


def compile_and_run_arm(src_text, stdin=""):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "prog.em"
        src.write_text(src_text)
        exe = build(src, Path(tmp) / "prog", target="linux-arm64")
        return run_command(exe, stdin)


class Arm64Compile(unittest.TestCase):
    def test_target_is_accepted_and_emits_aarch64(self):
        asm = compile_to_asm("def main():\n    print(1)\n", "linux-arm64")
        self.assertIn("bl ember_print_i64", asm)
        self.assertIn("stp x29, x30, [sp, #-16]!", asm)
        self.assertIn(".globl em_main", asm)
        self.assertNotIn("rbp", asm)              # no x86 register names leak through

    def test_entry_and_user_functions_are_global_symbols(self):
        asm = compile_to_asm("def f(x: i64) -> i64:\n    return x\n\ndef main():\n    print(f(2))\n",
                             "linux-arm64")
        self.assertIn(".globl em_f", asm)
        self.assertIn("bl em_f", asm)
        self.assertIn(".globl em_main", asm)

    def test_stack_note_marks_non_executable(self):
        asm = compile_to_asm("def main():\n    print(1)\n", "linux-arm64")
        self.assertIn('.section .note.GNU-stack,"",@progbits', asm)

    def test_window_builtins_rejected_outside_windows(self):
        with self.assertRaises(CompileError) as ctx:
            compile_to_asm("def main():\n    if window_open(10, 10):\n        print(1)\n", "linux-arm64")
        self.assertIn("only available when building for Windows", ctx.exception.msg)

    def test_division_uses_sdiv_and_msub(self):
        asm = compile_to_asm("def main():\n    print(7 % 2)\n", "linux-arm64")
        self.assertIn("sdiv", asm)
        self.assertIn("msub", asm)

    def test_x86_output_is_unchanged_by_the_new_backend(self):
        # The x86 generator must keep producing NASM for the default target.
        asm = compile_to_asm("def main():\n    print(1)\n")
        self.assertIn("section .text", asm)
        self.assertNotIn("sdiv", asm)


@unittest.skipUnless(CAN_RUN_ARM, "needs an AArch64 cross compiler plus qemu-aarch64 (or an ARM64 host)")
class Arm64Examples(unittest.TestCase):
    def test_every_example_produces_expected_output(self):
        for em in EXAMPLES:
            with self.subTest(program=em.name):
                stdin_file = em.with_suffix(".in")
                stdin = stdin_file.read_text() if stdin_file.exists() else ""
                proc = compile_and_run_arm(em.read_text(), stdin)
                self.assertEqual(proc.returncode, EXPECTED_EXIT.get(em.stem, 0), proc.stderr)
                self.assertEqual(proc.stdout, em.with_suffix(".out").read_text())


@unittest.skipUnless(CAN_RUN_ARM, "needs an AArch64 cross compiler plus qemu-aarch64 (or an ARM64 host)")
class Arm64Semantics(unittest.TestCase):
    def assertPanics(self, src, message, stdout=""):
        proc = compile_and_run_arm(src)
        self.assertEqual(proc.returncode, 101)
        self.assertIn(message, proc.stderr)
        self.assertEqual(proc.stdout, stdout)

    def test_division_by_zero_panics(self):
        self.assertPanics("def main():\n    print(7 / 0)\n", "division by zero")

    def test_modulo_by_zero_panics(self):
        self.assertPanics("def main():\n    print(7 % 0)\n", "division by zero")

    def test_index_out_of_bounds_panics_after_flushing_output(self):
        self.assertPanics("def main():\n    xs = [1, 2]\n    print(xs[0])\n    print(xs[2])\n",
                          "index out of bounds", stdout="1\n")

    def test_negative_alloc_panics(self):
        self.assertPanics("def main():\n    xs = alloc(0 - 1)\n", "out of memory")

    def test_min_divided_by_minus_one_wraps(self):
        src = ("def main():\n    m = -9223372036854775807 - 1\n"
               "    print(m / (0 - 1))\n    print(m % (0 - 1))\n")
        proc = compile_and_run_arm(src)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "-9223372036854775808\n0\n")

    def test_signed_division_and_modulo_truncate_toward_zero(self):
        src = ("def main():\n    print(0 - 7 / 2)\n    print((0 - 7) / 2)\n"
               "    print((0 - 7) % 2)\n    print(7 % (0 - 2))\n")
        self.assertEqual(compile_and_run_arm(src).stdout, "-3\n-3\n-1\n1\n")

    def test_large_integer_literals(self):
        src = "def main():\n    print(9223372036854775807)\n    print(0 - 9223372036854775807)\n"
        self.assertEqual(compile_and_run_arm(src).stdout, "9223372036854775807\n-9223372036854775807\n")

    def test_large_frame_uses_offsets_beyond_unscaled_range(self):
        # 40 locals is a 320-byte frame: slots past 256 bytes need the register-offset path.
        names = [f"v{i}" for i in range(40)]
        lines = [f"    {name} = {i}" for i, name in enumerate(names)]
        lines.append("    print(v0 + v39 + v33)")
        src = "def main():\n" + "\n".join(lines) + "\n"
        self.assertEqual(compile_and_run_arm(src).stdout, "72\n")

    def test_arguments_and_recursion(self):
        src = ("def add4(a: i64, b: i64, c: i64, d: i64) -> i64:\n"
               "    return a * 1000 + b * 100 + c * 10 + d\n\n"
               "def fact(n: i64) -> i64:\n    if n < 2:\n        return 1\n"
               "    return n * fact(n - 1)\n\n"
               "def main():\n    print(add4(1, 2, 3, 4))\n    print(fact(10))\n")
        self.assertEqual(compile_and_run_arm(src).stdout, "1234\n3628800\n")

    def test_arrays_are_shared_by_reference(self):
        src = ("def fill(a: [i64]):\n    for i in range(len(a)):\n        a[i] = i * i\n\n"
               "def main():\n    xs = alloc(4)\n    fill(xs)\n    print(xs[3])\n    ys = [7, 8]\n"
               "    print(ys[0] + ys[1])\n")
        self.assertEqual(compile_and_run_arm(src).stdout, "9\n15\n")

    def test_short_circuit_skips_side_effects(self):
        src = ("def boom() -> bool:\n    xs = alloc(0)\n    return xs[0] == 0\n\n"
               "def main():\n    if false and boom():\n        print(1)\n    if true or boom():\n        print(2)\n")
        self.assertEqual(compile_and_run_arm(src).stdout, "2\n")

    def test_comparisons_and_not(self):
        src = ("def main():\n    if 3 >= 3 and not (2 == 3):\n        print(1)\n"
               "    print(2 != 2)\n    print(0 - 1 < 0)\n")
        self.assertEqual(compile_and_run_arm(src).stdout, "1\nfalse\ntrue\n")

    def test_break_and_continue(self):
        src = ("def main():\n    for i in range(10):\n        if i == 2:\n            continue\n"
               "        if i == 5:\n            break\n        print(i)\n")
        self.assertEqual(compile_and_run_arm(src).stdout, "0\n1\n3\n4\n")


@unittest.skipUnless(CAN_RUN_ARM, "needs an AArch64 cross compiler plus qemu-aarch64 (or an ARM64 host)")
class Arm64Cli(unittest.TestCase):
    def test_cli_builds_arm64_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fib_arm"
            proc = subprocess.run(
                [sys.executable, "-m", "ember", "build", str(ROOT / "examples" / "fib.em"),
                 "--target", "linux-arm64", "-o", str(out)],
                capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(run_command(out).stdout, (ROOT / "examples" / "fib.out").read_text())


if __name__ == "__main__":
    unittest.main()
