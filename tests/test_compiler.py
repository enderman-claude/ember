import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import build, compile_to_asm  # noqa: E402
from ember.errors import CompileError          # noqa: E402
from ember.lexer import tokenize               # noqa: E402
from ember.parser import parse                 # noqa: E402

HAVE_TOOLS = bool(shutil.which("nasm") and shutil.which("cc"))
GOOD = "def main():\n    print(1)\n"


def compile_error(src):
    try:
        compile_to_asm(src)
    except CompileError as e:
        return e
    raise AssertionError("expected a CompileError")


class LexerTests(unittest.TestCase):
    def test_indent_and_dedent_tokens(self):
        kinds = [t.kind for t in tokenize("def main():\n    print(1)\n")]
        self.assertEqual(kinds, [
            "def", "NAME", "(", ")", ":", "NEWLINE", "INDENT",
            "NAME", "(", "INT", ")", "NEWLINE", "DEDENT", "EOF",
        ])

    def test_comments_and_blank_lines_are_ignored(self):
        kinds = [t.kind for t in tokenize("# header\n\ndef main():  # entry\n    print(1)\n")]
        self.assertEqual(kinds[0], "def")

    def test_tabs_rejected(self):
        with self.assertRaises(CompileError):
            tokenize("def main():\n\tprint(1)\n")

    def test_inconsistent_dedent_rejected(self):
        with self.assertRaises(CompileError):
            tokenize("def main():\n    x = 1\n  y = 2\n")


class ParserTests(unittest.TestCase):
    def test_top_level_statement_rejected(self):
        e = compile_error("x = 1\ndef main():\n    print(1)\n")
        self.assertIn("top-level statements are not allowed", e.msg)
        self.assertEqual(e.line, 1)

    def test_operator_precedence(self):
        prog = parse("def main():\n    print(1 + 2 * 3)\n")
        expr = prog.funcs[0].body[0].expr.args[0]
        self.assertEqual(expr.op, "+")
        self.assertEqual(expr.right.op, "*")

    def test_elif_else_chain_parses(self):
        prog = parse("def f(x: i64) -> i64:\n    if x < 0:\n        return 1\n"
                     "    elif x == 0:\n        return 2\n    else:\n        return 3\n\n"
                     "def main():\n    print(f(1))\n")
        self.assertEqual(len(prog.funcs[0].body[0].branches), 2)
        self.assertIsNotNone(prog.funcs[0].body[0].else_body)

    def test_unknown_type_rejected(self):
        e = compile_error("def main(x: f64):\n    print(1)\n")
        self.assertIn("unknown type", e.msg)


class EntryPointTests(unittest.TestCase):
    def test_valid_main_compiles(self):
        compile_to_asm(GOOD)

    def test_missing_main(self):
        e = compile_error("def greet():\n    print(1)\n")
        self.assertIn("no entry point", e.msg)

    def test_main_with_parameters(self):
        e = compile_error("def main(x: i64):\n    print(x)\n")
        self.assertIn("must take no parameters", e.msg)

    def test_duplicate_main(self):
        e = compile_error(GOOD + "\ndef main():\n    print(2)\n")
        self.assertIn("multiple definitions of main()", e.msg)


class TypeCheckTests(unittest.TestCase):
    def test_bool_arithmetic_rejected(self):
        e = compile_error("def main():\n    print(true + 1)\n")
        self.assertIn("expected i64, found bool", e.msg)

    def test_assign_to_immutable_rejected(self):
        e = compile_error("def main():\n    x = 1\n    x = 2\n")
        self.assertIn("immutable", e.msg)

    def test_mut_reassignment_allowed(self):
        compile_to_asm("def main():\n    mut x = 1\n    x = 2\n    print(x)\n")

    def test_if_condition_must_be_bool(self):
        e = compile_error("def main():\n    if 1:\n        print(1)\n")
        self.assertIn("if condition", e.msg)

    def test_undefined_name(self):
        e = compile_error("def main():\n    print(nope)\n")
        self.assertIn("undefined name 'nope'", e.msg)

    def test_block_scope_is_enforced(self):
        e = compile_error("def main():\n    if true:\n        y = 1\n    print(y)\n")
        self.assertIn("undefined name 'y'", e.msg)

    def test_branch_local_names_may_repeat(self):
        compile_to_asm("def main():\n    if true:\n        x = 1\n        print(x)\n"
                       "    else:\n        x = 2\n        print(x)\n")

    def test_missing_return_rejected(self):
        e = compile_error("def f(x: i64) -> i64:\n    if x > 0:\n        return 1\n\n"
                          "def main():\n    print(f(1))\n")
        self.assertIn("may finish without returning", e.msg)

    def test_if_else_both_returning_is_accepted(self):
        compile_to_asm("def f(x: i64) -> i64:\n    if x > 0:\n        return 1\n"
                       "    else:\n        return 2\n\ndef main():\n    print(f(1))\n")

    def test_wrong_arity(self):
        e = compile_error("def f(a: i64) -> i64:\n    return a\n\ndef main():\n    print(f(1, 2))\n")
        self.assertIn("takes 1 argument(s), got 2", e.msg)

    def test_builtin_cannot_be_redefined(self):
        e = compile_error("def print(x: i64):\n    return\n\ndef main():\n    print(1)\n")
        self.assertIn("builtin", e.msg)

    def test_integer_literal_range(self):
        e = compile_error("def main():\n    print(9223372036854775808)\n")
        self.assertIn("does not fit in i64", e.msg)


class CodegenTests(unittest.TestCase):
    def test_entry_symbol_emitted(self):
        asm = compile_to_asm(GOOD)
        self.assertIn("global em_main", asm)
        self.assertIn("em_main:", asm)

    def test_builtin_is_declared_extern(self):
        self.assertIn("extern ember_print_i64", compile_to_asm(GOOD))


@unittest.skipUnless(HAVE_TOOLS, "nasm and cc are required for end-to-end tests")
class EndToEndTests(unittest.TestCase):
    def run_program(self, src):
        with tempfile.TemporaryDirectory() as tmp:
            src_file = Path(tmp) / "prog.em"
            src_file.write_text(src)
            exe = build(src_file, Path(tmp) / "prog")
            return subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout

    def run_example(self, name):
        return self.run_program((ROOT / "examples" / name).read_text())

    def test_hello(self):
        self.assertEqual(self.run_example("hello.em"), "42\n40\n")

    def test_recursion_fib(self):
        self.assertEqual(self.run_example("fib.em"),
                         "0\n1\n1\n2\n3\n5\n8\n13\n21\n34\n")

    def test_elif_and_modulo(self):
        self.assertEqual(self.run_example("sign.em"), "-1\n0\n1\n4\n")

    def test_primes_with_short_circuit_and(self):
        self.assertEqual(self.run_example("primes.em"), "2\n3\n7\n11\n19\n23\n6\n")

    def test_gcd_loop(self):
        self.assertEqual(self.run_example("gcd.em"), "6\n1\n21\n")

    def test_deep_expression_keeps_stack_aligned(self):
        # Calls nested inside arithmetic exercise the rsp alignment around call sites.
        src = ("def id(x: i64) -> i64:\n    return x\n\n"
               "def main():\n    print(1 + (2 * (id(3) + (4 - id(5)))))\n")
        self.assertEqual(self.run_program(src), "5\n")  # 1 + 2 * (3 + (4 - 5))

    def test_comparisons_and_not(self):
        src = ("def main():\n    if 3 >= 3 and not (2 == 3):\n        print(1)\n"
               "    if 1 != 1 or false:\n        print(0)\n    else:\n        print(7)\n")
        self.assertEqual(self.run_program(src), "1\n7\n")


if __name__ == "__main__":
    unittest.main()
