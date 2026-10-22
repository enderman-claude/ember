# Ember

Ember is a small, statically typed language with Python-style syntax that compiles
directly to native x86-64 assembly. There's no interpreter, bytecode, VM, or garbage collector.
The compiler emits NASM, assembles it, and links it with a tiny C runtime.

```
def fib(n: i64) -> i64:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

def main():
    mut i = 0
    while i < 10:
        print(fib(i))
        i = i + 1
```

```
$ python -m ember run examples/fib.em
0
1
1
2
...
```

## Status

Ember is at an early stage. The implemented subset is complete and tested end to end.
Structs, enums, `match`, strings, generics, arrays, and `unsafe` are designed but not implemented yet.

### Implemented (v0.1)

- Types: `i64`, `bool`, and `unit` (the implicit return type of functions with no `->`)
- Bindings: `x = e` (immutable, declared on first assignment), `mut x = e`, and reassignment of `mut` bindings
- Block scoping, like Rust: a name lives in the block where it was declared
- Operators: `+ - * / %`, comparisons `== != < <= > >=`, `and`, `or` (short-circuit), `not`, unary `-`
- Control flow: `if` / `elif` / `else`, `while`, `return`
- Functions: up to 6 parameters, recursion, and forward references
- Builtin: `print(x: i64)`
- Entry point: exactly one parameterless `def main()` is required. Top-level statements are compile errors.
- Static checks: name resolution, type checking, immutability, missing returns, arity, integer literal range

### Not yet implemented

Structs, enums and `match`, strings and floats, arrays, `Option`/`Result`, generics, `unsafe` pointers,
imports, and inline assembly. The long-term design is in the project history.

## Usage

Requires Python 3.10+, `nasm`, and a C compiler (`cc`) on `PATH`.

```
python -m ember check   prog.em          # type-check only
python -m ember build   prog.em -o prog  # produce a native executable
python -m ember run     prog.em          # compile and run
python -m ember emit-asm prog.em         # print the generated NASM
```

After `pip install .`, the same commands are available as `ember`.

Compile errors report the file, line, and message:

```
prog.em: error: line 3: cannot assign to immutable 'x' (declare it with `mut`)
```

## Architecture

```
source ─► lexer ─► parser ─► checker ─► codegen ─► nasm ─► cc (+ runtime) ─► executable
          tokens    AST       typed AST    .asm       .o
```

| Module | Responsibility |
|---|---|
| `ember/lexer.py` | Indentation-aware tokenizer. Emits `INDENT`/`DEDENT`/`NEWLINE`. |
| `ember/parser.py` | Recursive-descent parser with explicit precedence levels. |
| `ember/nodes.py` | AST dataclasses. |
| `ember/checker.py` | Entry-point rule, scopes, type checking, and return analysis. |
| `ember/codegen.py` | x86-64 codegen. Results in `rax`, a frame slot per variable, System V calls. |
| `ember/runtime/ember_rt.c` | C `main` that calls `em_main`, plus builtins such as `print`. |
| `ember/driver.py` | Runs the toolchain and manages temporary files. |
| `ember/cli.py` | Command-line interface. |

### Codegen notes

- Every Ember function `f` becomes the symbol `em_f`, so user names can't collide with libc.
- Calls align `rsp` to 16 bytes at each call site by saving `rsp` in `rbx`, which keeps
  C interop correct regardless of expression depth.
- Each local has its own 8-byte frame slot, and all slots are zeroed in the prologue.
- Integer division by zero triggers a hardware trap (SIGFPE). A checked version is planned.

## Tests

```
python -m unittest discover -s tests -v
```

The suite covers the lexer, parser, entry-point rules, type errors, and codegen. The end-to-end
tests build and run each example program and compare its output. They are skipped if `nasm` or `cc` is missing.

## Layout

```
ember/       compiler package
examples/    sample programs
tests/       unit and end-to-end tests
```

## License

MIT
