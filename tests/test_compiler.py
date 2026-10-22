"""Front-end and code-generator tests: parsing, type checking and error messages."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import compile_to_asm  # noqa: E402
from ember.errors import CompileError    # noqa: E402
from ember.lexer import tokenize         # noqa: E402
from ember.parser import parse           # noqa: E402

GOOD = "def main():\n    print(1)\n"


def compile_error(src):
    try:
        compile_to_asm(src)
    except CompileError as e:
        return e
    raise AssertionError("expected a CompileError")


def body(stmts):
    """Wrap statements in a main() so each test stays short."""
    return "def main():\n" + "".join(f"    {line}\n" for line in stmts.splitlines())


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

    def test_crlf_line_endings(self):
        self.assertEqual(compile_to_asm("def main():\r\n    print(1)\r\n"), compile_to_asm(GOOD))

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
        prog = parse(GOOD.replace("print(1)", "print(1 + 2 * 3)"))
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
        self.assertIn("unknown type", compile_error("def main(x: f64):\n    print(1)\n").msg)

    def test_only_i64_arrays(self):
        self.assertIn("only arrays of i64", compile_error("def main(x: [bool]):\n    print(1)\n").msg)

    def test_assignment_to_non_name_needs_index(self):
        e = compile_error(body("1 = 2"))
        self.assertIn("left side of '='", e.msg)

    def test_for_requires_range(self):
        e = compile_error(body("for i in xs:\n    print(i)"))
        self.assertIn("only `for x in range", e.msg)

    def test_trailing_comma_in_array_literal(self):
        compile_to_asm(body("xs = [1, 2, 3,]\nprint(xs[0])"))


class EntryPointTests(unittest.TestCase):
    def test_valid_main_compiles(self):
        compile_to_asm(GOOD)

    def test_missing_main(self):
        self.assertIn("no entry point", compile_error("def greet():\n    print(1)\n").msg)

    def test_main_with_parameters(self):
        self.assertIn("must take no parameters",
                      compile_error("def main(x: i64):\n    print(x)\n").msg)

    def test_main_with_return_type(self):
        self.assertIn("must not return a value",
                      compile_error("def main() -> i64:\n    return 1\n").msg)

    def test_duplicate_main(self):
        self.assertIn("multiple definitions of main()",
                      compile_error(GOOD + "\ndef main():\n    print(2)\n").msg)


class TypeCheckTests(unittest.TestCase):
    def assertError(self, src, fragment):
        self.assertIn(fragment, compile_error(src).msg)

    def test_bool_arithmetic_rejected(self):
        self.assertError(body("print(true + 1)"), "expected i64, found bool")

    def test_assign_to_immutable_rejected(self):
        self.assertError(body("x = 1\nx = 2"), "immutable")

    def test_mut_reassignment_allowed(self):
        compile_to_asm(body("mut x = 1\nx = 2\nprint(x)"))

    def test_binding_unit_rejected(self):
        self.assertError(body("x = print(1)"), "has no value")

    def test_print_bool_allowed(self):
        compile_to_asm(body("print(true)"))

    def test_print_array_rejected(self):
        self.assertError(body("print(alloc(2))"), "print() takes i64 or bool")

    def test_if_condition_must_be_bool(self):
        self.assertError(body("if 1:\n    print(1)"), "if condition")

    def test_undefined_name(self):
        self.assertError(body("print(nope)"), "undefined name 'nope'")

    def test_block_scope_is_enforced(self):
        self.assertError(body("if true:\n    y = 1\nprint(y)"), "undefined name 'y'")

    def test_branch_local_names_may_repeat(self):
        compile_to_asm(body("if true:\n    x = 1\n    print(x)\nelse:\n    x = 2\n    print(x)"))

    def test_missing_return_rejected(self):
        self.assertError("def f(x: i64) -> i64:\n    if x > 0:\n        return 1\n\n"
                         "def main():\n    print(f(1))\n", "may finish without returning")

    def test_if_else_both_returning_is_accepted(self):
        compile_to_asm("def f(x: i64) -> i64:\n    if x > 0:\n        return 1\n"
                       "    else:\n        return 2\n\ndef main():\n    print(f(1))\n")

    def test_wrong_arity(self):
        self.assertError("def f(a: i64) -> i64:\n    return a\n\ndef main():\n    print(f(1, 2))\n",
                         "takes 1 argument(s), got 2")

    def test_builtin_cannot_be_redefined(self):
        self.assertError("def len(x: i64) -> i64:\n    return x\n\ndef main():\n    print(1)\n",
                         "builtin")

    def test_integer_literal_range(self):
        self.assertError(body("print(9223372036854775808)"), "does not fit in i64")

    def test_index_non_array(self):
        self.assertError(body("x = 5\nprint(x[0])"), "cannot index a value of type i64")

    def test_array_element_type(self):
        self.assertError(body("xs = [1, true]"), "array literal element")

    def test_empty_array_literal(self):
        self.assertError(body("xs = []"), "empty array literals")

    def test_break_outside_loop(self):
        self.assertError(body("break"), "'break' outside of a loop")

    def test_continue_outside_loop(self):
        self.assertError(body("if true:\n    continue"), "'continue' outside of a loop")

    def test_loop_variable_is_immutable(self):
        self.assertError(body("for i in range(3):\n    i = 5"), "immutable")

    def test_range_bounds_must_be_i64(self):
        self.assertError(body("for i in range(true):\n    print(i)"), "range stop")

    def test_array_parameter_and_return(self):
        compile_to_asm("def copy(a: [i64]) -> [i64]:\n    return a\n\n"
                       "def main():\n    b = copy(alloc(3))\n    print(len(b))\n")


class CodegenTests(unittest.TestCase):
    def test_entry_symbol_emitted(self):
        asm = compile_to_asm(GOOD)
        self.assertIn("global em_main", asm)
        self.assertIn("em_main:", asm)

    def test_runtime_symbols_declared(self):
        asm = compile_to_asm(GOOD)
        for sym in ("ember_print_i64", "ember_load", "ember_store", "ember_panic"):
            self.assertIn(f"extern {sym}", asm)

    def test_output_is_deterministic(self):
        src = (ROOT / "examples" / "sieve.em").read_text()
        self.assertEqual(compile_to_asm(src), compile_to_asm(src))


@unittest.skipUnless(shutil.which("python3"), "python3 required")
class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "ember", *args],
                              cwd=ROOT, capture_output=True, text=True)

    def test_check_ok_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ok.em"
            f.write_text(GOOD)
            proc = self.run_cli("check", str(f))
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "ok")

    def test_compile_error_exit_one_with_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.em"
            f.write_text(body("x = 1\nx = 2"))
            proc = self.run_cli("check", str(f))
            self.assertEqual(proc.returncode, 1)
            self.assertIn("bad.em: error: line", proc.stderr)
            self.assertIn("immutable", proc.stderr)

    def test_missing_file_exit_two(self):
        proc = self.run_cli("check", "/nonexistent/file.em")
        self.assertEqual(proc.returncode, 2)




class TargetTests(unittest.TestCase):
    def test_window_builtins_rejected_on_linux(self):
        src = "def main():\n    ok = window_open(10, 10)\n"
        self.assertIn("only available when building for Windows", compile_error(src).msg)

    def test_window_builtins_accepted_for_windows(self):
        asm = compile_to_asm("def main():\n    if window_open(10, 10):\n        print(1)\n", "windows")
        self.assertIn("extern ember_window_open", asm)

    def test_windows_target_uses_win64_argument_registers(self):
        asm = compile_to_asm("def f(a: i64, b: i64) -> i64:\n    return a + b\n\n"
                             "def main():\n    print(f(1, 2))\n", "windows")
        self.assertIn("pop rdx", asm)
        self.assertNotIn("pop rsi", asm)
        self.assertIn("sub rsp, 32", asm)           # shadow space
        self.assertNotIn("section .note.GNU-stack", asm)

    def test_linux_target_keeps_sysv_registers(self):
        asm = compile_to_asm("def f(a: i64, b: i64) -> i64:\n    return a + b\n\n"
                             "def main():\n    print(f(1, 2))\n", "linux")
        self.assertIn("pop rsi", asm)
        self.assertIn("section .note.GNU-stack", asm)

    def test_more_than_four_parameters_rejected(self):
        src = "def f(a: i64, b: i64, c: i64, d: i64, e: i64):\n    print(a)\n\ndef main():\n    print(1)\n"
        self.assertIn("at most 4 parameters", compile_error(src).msg)


if __name__ == "__main__":
    unittest.main()
