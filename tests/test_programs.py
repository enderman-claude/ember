"""End-to-end tests: compile real programs with nasm and cc, run them, and compare output.

Each examples/NAME.em is run with examples/NAME.in (if present) on stdin and its
stdout is compared with examples/NAME.out. EXPECTED_EXIT lists programs that are
supposed to stop with a runtime panic.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import build  # noqa: E402

HAVE_TOOLS = bool(shutil.which("nasm") and shutil.which("cc"))
EXPECTED_EXIT = {"bounds_demo": 101}
EXAMPLES = sorted((ROOT / "examples").glob("*.em"))


def compile_and_run(src_text, stdin=""):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "prog.em"
        src.write_text(src_text)
        exe = build(src, Path(tmp) / "prog")
        return subprocess.run([str(exe)], input=stdin, capture_output=True, text=True, timeout=20)


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required for end-to-end tests")
class ExamplePrograms(unittest.TestCase):
    def test_every_example_has_expected_output(self):
        for em in EXAMPLES:
            self.assertTrue(em.with_suffix(".out").exists(), f"{em.name} has no .out file")

    def test_examples_produce_expected_output(self):
        for em in EXAMPLES:
            with self.subTest(program=em.name):
                stdin_file = em.with_suffix(".in")
                stdin = stdin_file.read_text() if stdin_file.exists() else ""
                proc = compile_and_run(em.read_text(), stdin)
                want_exit = EXPECTED_EXIT.get(em.stem, 0)
                self.assertEqual(proc.returncode, want_exit, proc.stderr)
                self.assertEqual(proc.stdout, em.with_suffix(".out").read_text())


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required for end-to-end tests")
class RuntimeSemantics(unittest.TestCase):
    def assertPanics(self, src, message, stdout=""):
        proc = compile_and_run(src)
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

    def test_negative_index_panics(self):
        self.assertPanics("def main():\n    xs = [1]\n    print(xs[0 - 1])\n", "index out of bounds")

    def test_negative_alloc_panics(self):
        self.assertPanics("def main():\n    xs = alloc(0 - 1)\n", "out of memory")

    def test_min_divided_by_minus_one_wraps(self):
        src = ("def main():\n    m = -9223372036854775807 - 1\n"
               "    print(m / (0 - 1))\n    print(m % (0 - 1))\n")
        proc = compile_and_run(src)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "-9223372036854775808\n0\n")

    def test_signed_division_and_modulo_truncate_toward_zero(self):
        src = ("def main():\n    print(0 - 7 / 2)\n    print((0 - 7) / 2)\n"
               "    print((0 - 7) % 2)\n    print(7 % (0 - 2))\n")
        proc = compile_and_run(src)
        self.assertEqual(proc.stdout, "-3\n-3\n-1\n1\n")

    def test_break_and_continue(self):
        src = ("def main():\n    for i in range(10):\n        if i == 2:\n            continue\n"
               "        if i == 5:\n            break\n        print(i)\n")
        self.assertEqual(compile_and_run(src).stdout, "0\n1\n3\n4\n")

    def test_break_only_leaves_innermost_loop(self):
        src = ("def main():\n    for i in range(3):\n        for j in range(3):\n"
               "            if j == 1:\n                break\n            print(i * 10 + j)\n")
        self.assertEqual(compile_and_run(src).stdout, "0\n10\n20\n")

    def test_for_bounds_evaluated_once(self):
        src = ("def main():\n    mut n = 3\n    for i in range(n):\n        n = n + 1\n        print(i)\n"
               "    print(n)\n")
        self.assertEqual(compile_and_run(src).stdout, "0\n1\n2\n6\n")

    def test_for_stop_expression_sees_outer_name(self):
        src = "def main():\n    i = 4\n    for i in range(i):\n        print(i)\n"
        self.assertEqual(compile_and_run(src).stdout, "0\n1\n2\n3\n")

    def test_arrays_are_shared_by_reference(self):
        src = ("def fill(a: [i64]):\n    for i in range(len(a)):\n        a[i] = i * i\n\n"
               "def main():\n    xs = alloc(4)\n    fill(xs)\n    print(xs[3])\n")
        self.assertEqual(compile_and_run(src).stdout, "9\n")

    def test_locals_are_zeroed(self):
        src = "def main():\n    xs = alloc(3)\n    mut x = 0\n    print(xs[1] + x)\n"
        self.assertEqual(compile_and_run(src).stdout, "0\n")

    def test_deep_nested_calls_keep_stack_aligned(self):
        src = ("def id(x: i64) -> i64:\n    return x\n\n"
               "def main():\n    print(1 + (2 * (id(3) + (4 - id(5)))))\n")
        self.assertEqual(compile_and_run(src).stdout, "5\n")

    def test_short_circuit_skips_side_effects(self):
        src = ("def boom() -> bool:\n    xs = alloc(0)\n    return xs[0] == 0\n\n"
               "def main():\n    if false and boom():\n        print(1)\n"
               "    if true or boom():\n        print(2)\n")
        proc = compile_and_run(src)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "2\n")

    def test_comparisons_and_not(self):
        src = ("def main():\n    if 3 >= 3 and not (2 == 3):\n        print(1)\n"
               "    if 1 != 1 or false:\n        print(0)\n    else:\n        print(7)\n")
        self.assertEqual(compile_and_run(src).stdout, "1\n7\n")

    def test_read_int_reports_end_of_input(self):
        src = ("def main():\n    print(read_int())\n    print(input_ended())\n"
               "    print(read_int())\n    print(input_ended())\n")
        self.assertEqual(compile_and_run(src, "42").stdout, "42\nfalse\n0\ntrue\n")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required for end-to-end tests")
class GraphicsOutput(unittest.TestCase):
    """The graphics example writes a binary BMP, so this test reads stdout as bytes."""

    def test_graphics_test_writes_valid_bmp(self):
        import struct
        with tempfile.TemporaryDirectory() as tmp:
            exe = build(ROOT / "examples" / "graphics" / "graphics_test.em", Path(tmp) / "gfx")
            proc = subprocess.run([str(exe)], capture_output=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
        data = proc.stdout
        sig, size, _, _, offset = struct.unpack_from("<2sIHHI", data, 0)
        dib_size, w, h, planes, bpp, compression = struct.unpack_from("<IiiHHI", data, 14)
        self.assertEqual((sig, offset, dib_size, planes, bpp, compression), (b"BM", 54, 40, 1, 24, 0))
        self.assertEqual((w, h), (320, 240))
        row = w * 3 + (4 - (w * 3) % 4) % 4
        self.assertEqual(size, len(data))
        self.assertEqual(len(data), 54 + row * h)

        def pixel(x, y):              # BMP rows are stored bottom-up, pixels as BGR
            i = offset + (h - 1 - y) * row + x * 3
            return (data[i + 2], data[i + 1], data[i])

        self.assertEqual(pixel(50, 60), (230, 40, 40))     # rectangle
        self.assertEqual(pixel(230, 150), (250, 210, 30))  # circle centre
        self.assertEqual(pixel(250, 10), (255, 255, 255))  # checkerboard
        self.assertEqual(pixel(254, 10), (0, 0, 0))
        self.assertEqual(pixel(0, 0), (255, 255, 255))     # border
        self.assertEqual(pixel(1, 1), (0, 1, 160))         # gradient


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required for end-to-end tests")
class ForeignFunctions(unittest.TestCase):
    """extern def calls into C code supplied with --link."""

    def test_extern_calls_reach_c_implementations(self):
        from ember.driver import build as build_with_link
        impl = ROOT / "examples" / "ffi" / "extern_demo_impl.c"
        with tempfile.TemporaryDirectory() as tmp:
            exe = build_with_link(ROOT / "examples" / "ffi" / "extern_demo.em",
                                  Path(tmp) / "demo", "linux", link=[impl])
            proc = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "42\n7\n7\n")

    def test_extern_without_link_fails_at_link_time(self):
        from ember.driver import build as build_with_link
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                build_with_link(ROOT / "examples" / "ffi" / "extern_demo.em", Path(tmp) / "demo")
