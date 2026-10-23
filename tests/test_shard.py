"""Tests for --target shard: Ember programs packed into SHARD images with elfpack.

The images are checked by converting them back to ELF with shardelf (from the shard
repo) and running the result on Linux. The tests are skipped when nasm, cc, elfpack
or shardelf is missing. Set EMBER_ELFPACK and EMBER_SHARDELF to point at the tools,
or put them on PATH.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import build  # noqa: E402
from ember.errors import CompileError  # noqa: E402
from ember.driver import compile_to_asm  # noqa: E402

ELFPACK = os.environ.get("EMBER_ELFPACK") or shutil.which("elfpack")
SHARDELF = os.environ.get("EMBER_SHARDELF") or shutil.which("shardelf")
HAVE_TOOLS = bool(shutil.which("nasm") and shutil.which("cc") and ELFPACK and SHARDELF)


def run_shard(src_text, stdin=""):
    """Build src_text as a SHARD image, convert it to ELF and run it."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "prog.em"
        src.write_text(src_text)
        image = build(src, Path(tmp) / "prog.shard", target="shard")
        so = Path(tmp) / "prog.so"
        subprocess.run([SHARDELF, str(image), str(so)], check=True, capture_output=True)
        so.chmod(0o755)
        return subprocess.run([str(so)], input=stdin, capture_output=True, text=True, timeout=20)


@unittest.skipUnless(HAVE_TOOLS, "needs nasm, cc, elfpack and shardelf")
class ShardTargetTests(unittest.TestCase):

    def test_prints_numbers_and_bools(self):
        r = run_shard("def main():\n    print(7)\n    print(-42)\n    print(false)\n")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "7\n-42\nfalse\n")

    def test_arrays_round_trip_and_free(self):
        r = run_shard("def main():\n    a = alloc(4)\n    a[3] = 99\n    print(len(a))\n"
                      "    print(a[3])\n    free(a)\n")
        self.assertEqual(r.stdout, "4\n99\n")

    def test_index_out_of_bounds_panics_with_exit_101(self):
        r = run_shard("def main():\n    a = alloc(2)\n    print(a[5])\n")
        self.assertEqual(r.returncode, 101)
        self.assertIn("array index out of bounds", r.stderr)

    def test_read_int_and_input_ended(self):
        src = ("def main():\n    print(read_int() + read_int())\n"
               "    print(read_int())\n    print(input_ended())\n")
        r = run_shard(src, stdin="  20\n-5\n")
        self.assertEqual(r.stdout, "15\n0\ntrue\n")

    def test_matches_linux_output_for_fib(self):
        src = ("def fib(n: i64) -> i64:\n    if n < 2:\n        return n\n"
               "    return fib(n - 1) + fib(n - 2)\n\ndef main():\n"
               "    for i in range(10):\n        print(fib(i))\n")
        r = run_shard(src)
        self.assertEqual(r.stdout, "0\n1\n1\n2\n3\n5\n8\n13\n21\n34\n")


class ShardRestrictionTests(unittest.TestCase):

    def test_extern_is_rejected_for_shard(self):
        src = "extern def c_add(a: i64, b: i64) -> i64\n\ndef main():\n    print(c_add(1, 2))\n"
        with self.assertRaises(CompileError) as cm:
            compile_to_asm(src, "shard")
        self.assertIn("not available for --target shard", str(cm.exception))

    def test_window_builtins_are_rejected_for_shard(self):
        with self.assertRaises(CompileError):
            compile_to_asm("def main():\n    print(window_closed())\n", "shard")

    def test_link_flags_are_rejected_for_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "prog.em"
            src.write_text("def main():\n    print(1)\n")
            with self.assertRaises(RuntimeError):
                build(src, Path(tmp) / "out", target="shard", link=["-lm"])


if __name__ == "__main__":
    unittest.main()
