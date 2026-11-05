# Ember

[![ci](https://github.com/enderman-claude/ember/actions/workflows/ci.yml/badge.svg)](https://github.com/enderman-claude/ember/actions/workflows/ci.yml)

Ember is a small, statically typed language with Python-style syntax. It compiles
directly to native x86-64 or AArch64 assembly: no interpreter, no bytecode, no virtual
machine, no garbage collector. The compiler writes assembly (NASM for x86-64, GNU assembler
syntax for AArch64), assembles it, and links it against a small C runtime.

```python
def fib(n: i64) -> i64:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

def main():
    for i in range(10):
        print(fib(i))
```

```
$ ember run fib.em
0
1
1
2
3
5
8
13
21
34
```

## Install

Requires Python 3.10+, `nasm`, and a C compiler (`cc`) on `PATH`. On Debian or Ubuntu:

```
sudo apt-get install nasm build-essential
pip install git+https://github.com/enderman-claude/ember.git
```

Or run it from a clone without installing:

```
git clone https://github.com/enderman-claude/ember.git && cd ember
python -m ember run examples/fib.em
```

## ARM64 (AArch64) Linux

`--target linux-arm64` produces an AArch64 ELF executable with the same language, runtime and
behaviour as the x86-64 build. Its generated assembly uses the AAPCS64 calling convention and
GNU assembler syntax, so it needs no NASM: gcc assembles and links it.

On an ARM64 Linux machine, build with the native `cc`:

```
ember build examples/fib.em --target linux-arm64 -o fib
./fib
```

On an x86-64 machine, install the GNU cross compiler and qemu-user to build and run it:

```
sudo apt-get install gcc-aarch64-linux-gnu qemu-user
ember build examples/fib.em --target linux-arm64 -o fib
qemu-aarch64 -L /usr/aarch64-linux-gnu ./fib
```

The cross compiler is `aarch64-linux-gnu-gcc` by default. Set `EMBER_ARM64_CC` to use a
different one. `ember run` always runs on the host, so use `build` and then run the
executable for AArch64. Window builtins are not available on this target.

## Windows programs

`--target windows` produces a 64-bit Windows GUI executable that uses only the system DLLs
(`user32`, `gdi32`, `kernel32`, `msvcrt`). It needs `nasm` and `x86_64-w64-mingw32-gcc`
(on Debian or Ubuntu: `sudo apt-get install nasm gcc-mingw-w64-x86-64`).

```
ember build examples/windows/window_test.em --target windows -o window_test.exe
```

Double-click the result on Windows 11. The window builtins below are available only for this target.

| Function | Signature | Description |
|---|---|---|
| `window_open` | `(i64, i64) -> bool` | Opens a window whose client area is width x height pixels |
| `window_present` | `([i64]) -> unit` | Copies a framebuffer to the window, handles window messages, and caps the rate at about 60 frames per second |
| `window_closed` | `() -> bool` | True once the user has closed the window |

A framebuffer is an `[i64]` array with one `0xRRGGBB` value per pixel, row by row from the
top. Its length must be at least the window's pixel count. `examples/windows/window_test.em`
animates a gradient with a moving circle.

## SHARD images

`--target shard` produces a SHARD image, the native binary format of tesseraOS (see
[enderman-claude/shard](https://github.com/enderman-claude/shard)). The program is compiled
to a freestanding static-pie ELF, which talks to the kernel directly instead of using libc,
then packed with `elfpack`. Install `elfpack` from the shard repo, put it on `PATH` or set
`EMBER_ELFPACK`.

```
ember build examples/fib.em --target shard -o fib.shard
```

SHARD has no dynamic linking, so `extern def`, `--link`, and the window builtins are not
available for this target. Everything else works the same as on Linux, including arrays,
`read_int`, and panics (exit code 101).

## Calling C

`extern def` declares a C function. Ember passes `i64` and `bool` arguments using the platform
calling convention, so the function can be written in C. Floats and bigfloats cannot cross
this boundary: convert them to `i64` first.

```python
extern def c_add(a: i64, b: i64) -> i64

def main():
    print(c_add(40, 2))
```

Link the implementation with `--link`:

```
ember run prog.em --link impl.c
ember run prog.em --link impl.c --link -lm
```

## Commands

```
ember check      prog.em                 type-check only
ember build      prog.em -o prog         produce a native executable (--target windows for .exe,
                                         --target linux-arm64 for AArch64)
ember run        prog.em                 compile and run (stdin and exit code pass through)
ember emit-asm   prog.em                 print the generated NASM assembly
```

Compile errors are reported with file and line, and exit with status 1:

```
prog.em: error: line 3: cannot assign to immutable 'x' (declare it with `mut`)
```

Runtime panics (division by zero, index out of bounds, failed allocation) print
`ember: panic: ...` to stderr and exit with status 101.

## Language guide

### Program structure

A program is a set of `def`s and must contain exactly one `def main():` with no
parameters and no return value. Only `def` may appear at the top level; any other
statement is a compile error, so all work starts from `main`.

```python
def main():
    print(1)
```

### Types

| Type | Meaning |
|---|---|
| `i64` | 64-bit signed integer. Arithmetic wraps on overflow. |
| `f64` | 64-bit IEEE 754 float. The type of a decimal literal such as `1.5`. |
| `f32` | 32-bit IEEE 754 float. Written with the suffix `f32`, as in `1.5f32`. |
| `bigfloat` | Exact rational number of any size, such as `100big / 3big`. Written with the suffix `big`. |
| `bool` | `true` or `false` |
| `[i64]` | Heap array of `i64`, bounds-checked, created with `alloc` or a literal |
| `unit` | The type of a function with no `->` clause. It has no value and can't be bound. |

Types are never converted implicitly. `1 + true` is an error, and so is `1 + 2.0`. Use a
conversion function to change a number's type: `f64(3)`, `f32(x)`, `bigfloat(x)`, `i64(x)`.

### Numbers

Literals: `1.5` is `f64`, `1.5f32` is `f32`, `1.5big` is `bigfloat`, and an integer with a
suffix is a number of that type too (`2big`). Underscores are allowed (`1_000.5`).

`f32` and `f64` follow IEEE 754: arithmetic rounds to nearest, `1.0 / 0.0` is `inf`, and
`0.0 / 0.0` is NaN, which is not equal to anything. Converting a float to `i64` truncates
toward zero and panics if the value does not fit. `%` is for `i64` only.

`bigfloat` is exact. Each value is a fraction kept in lowest terms, so `100big / 3big` is
stored as 100/3 and never rounded. Arithmetic and comparisons are exact. Division by zero
panics. A `bigfloat` has no negative zero. Converting a `bigfloat` to `f64` or `f32` rounds
to the nearest value. Bigfloat values are not freed, so a loop that creates many of them
keeps the memory until the program exits.

Printing a number gives the shortest decimal that reads back as the same value, with the same
plain/scientific rules as Python's `repr`: `0.1`, `1e-05`, `1.2345678901234567e+19`. A
`bigfloat` prints exactly when its decimal expansion ends, and otherwise with 40 digits and
`...`: `100big / 3big` prints `33.3333333333333333333333333333333333333333...`.

#### Math functions

`sqrt`, `sin`, `cos`, `tan`, `atan`, `atan2`, `exp`, `ln`, `floor`, `ceil` and `abs` take
`f64` (or `f32`) and return the same type; `atan2(y, x)` takes two of the same type. Angles
are in radians. They do not take `i64` or `bigfloat` (convert with `f64(x)` first, as a
bigfloat has no exact square root or sine), and because they are builtins you cannot define a
function with one of these names (a variable can have it).

```python
def distance(x1: f64, y1: f64, x2: f64, y2: f64) -> f64:   # four parameters is the limit
    dx = x2 - x1
    dy = y2 - y1
    return sqrt(dx * dx + dy * dy)
```

They are written in C with no libc or libm (`ember/runtime/ember_math.h`), so they work
unchanged on every target, SHARD included, and a program prints the same digits everywhere.

| Function | Accuracy versus a correctly rounded result |
|---|---|
| `sqrt`, `floor`, `ceil`, `abs` | exact (`sqrt` is correctly rounded) |
| `sin`, `cos`, `atan`, `atan2`, `exp`, `ln` | within 2 ulp |
| `tan` | within 4 ulp |

An ulp is the gap between adjacent floats. So `exp(1.0)` prints `2.7182818284590455`, one ulp
from `e`. `f32` versions compute in `f64` and round once. Special values follow IEEE 754:
`sqrt` of a negative is NaN, `ln(0.0)` is `-inf`, `exp(1000.0)` is `inf`. `sin`, `cos` and
`tan` are only accurate while the argument is below about 1.6 million in size; past that
they return NaN instead of a wrong answer.

### Bindings and assignment

```python
x = 5            # immutable binding; the type is inferred
mut count = 0    # mutable binding
count = count + 1
```

`x = e` declares `x` the first time it appears in a scope. Assigning to it again is an
error. `mut` bindings can be reassigned. Each block has its own scope, so a name
declared inside an `if` or loop isn't visible after the block ends.

### Functions

```python
def area(w: i64, h: i64) -> i64:
    return w * h
```

Parameters are immutable. Functions can be called before they are defined, and they can
recurse. Up to four parameters are supported (the Windows x64 convention passes four
arguments in registers), for `extern def` as well. A function with a `->` clause must end in a
`return`, or in an `if`/`elif`/`else` chain where every branch returns. The check is
conservative: a `return` inside a loop doesn't count, even if the loop always runs.

### Operators

From highest to lowest precedence:

| Operators | Notes |
|---|---|
| unary `-` | `i64` |
| `*` `/` `%` | `i64`, `f32`, `f64` or `bigfloat`, the same type on both sides. `%` is `i64` only. `/` and `%` truncate toward zero. Integer division by zero panics. |
| `+` `-` | `i64`, `f32`, `f64` or `bigfloat`, the same type on both sides |
| `==` `!=` `<` `<=` `>` `>=` | Same type on both sides. Don't chain. `a < b < c` is an error. |
| `not` | `bool` |
| `and` | `bool`, short-circuit |
| `or` | `bool`, short-circuit |

### Control flow

```python
if x < 0:
    print(-1)
elif x == 0:
    print(0)
else:
    print(1)

while n > 0:
    n = n - 1

for i in range(10):      # 0..9
    print(i)

for i in range(2, 8):    # 2..7
    if i == 4:
        continue
    if i == 6:
        break
    print(i)
```

`range` bounds are evaluated once, before the loop starts. Changing the loop variable has no
effect on the iteration.

### Arrays

```python
xs = [3, 1, 2]           # literal; elements must be i64, and the literal can't be empty
buf = alloc(100)         # 100 zeroed elements
print(len(xs))           # 3
print(xs[0])             # 3
xs[1] = 10
free(buf)                # every alloc needs one matching free
```

Arrays are references, so passing one to a function lets the function change its elements.
Indexing is bounds-checked and panics when the index is out of range. Memory is manual:
there is no garbage collector and no automatic free. Using an array after `free`, or freeing
it twice, is undefined behavior. A future version will add ownership rules that prevent this.

### Builtins

| Function | Signature | Description |
|---|---|---|
| `print` | `i64 \| bool \| f32 \| f64 \| bigfloat -> unit` | Writes the value and a newline to stdout |
| `i64`, `f32`, `f64`, `bigfloat` | `number -> number` | Converts between number types (see Numbers) |
| `alloc` | `i64 -> [i64]` | Allocates a zeroed array of the given length |
| `free` | `[i64] -> unit` | Releases an array |
| `len` | `[i64] -> i64` | Returns the array length |
| `read_int` | `() -> i64` | Reads the next integer from stdin. Returns 0 at end of input. |
| `input_ended` | `() -> bool` | True if the last `read_int` hit end of input |
| `put_byte` | `i64 -> unit` | Writes one raw byte (the low 8 bits) to stdout, for binary output |
| `sqrt`, `sin`, `cos`, `tan`, `atan`, `exp`, `ln`, `floor`, `ceil`, `abs` | `f64 -> f64` or `f32 -> f32` | Math functions (see Math functions) |
| `atan2` | `(f64, f64) -> f64` or `(f32, f32) -> f32` | Angle of the point (x, y), in radians |

## Examples

The `examples/` directory holds working programs, each with its expected output. Some also
have an `.in` file for stdin. Highlights:

- `sieve.em`: Sieve of Eratosthenes
- `nqueens.em`: backtracking search
- `knapsack.em`: dynamic programming, reads its input from stdin
- `matrix.em`: matrix multiplication on arrays
- `hanoi.em`: recursion and printed output
- `bubble_sort.em`: reads numbers from stdin and sorts them
- `windows/window_test.em`: animated window (Windows target)
- `graphics/graphics_test.em`: renders a framebuffer and writes a BMP to stdout (open the output in any image viewer)

Run the whole suite with `python -m unittest discover -s tests -v`. The AArch64 tests run
every example as an ARM64 executable, under qemu-user on x86-64 hosts or natively on ARM64,
and are skipped when neither is available.

## Implementation

```
source ─► lexer ─► parser ─► checker ─► codegen ─► nasm ─► cc (+ runtime) ─► executable
          tokens    AST       checked     .asm       .o
                              AST

linux-arm64:  checker ─► codegen_arm64 ─► cc (+ runtime) ─► executable      (.s, no nasm)
```

| Module | Responsibility |
|---|---|
| `ember/lexer.py` | Indentation-aware tokenizer. Emits `INDENT`, `DEDENT`, and `NEWLINE`. |
| `ember/parser.py` | Recursive-descent parser. Precedence is encoded in the function layout. |
| `ember/nodes.py` | AST dataclasses. |
| `ember/checker.py` | Entry-point rule, scopes, types, mutability, and return-path analysis. |
| `ember/codegen.py` | x86-64 code generation. Results go in `rax`. Each local has a frame slot. |
| `ember/codegen_arm64.py` | AArch64 code generation (AAPCS64, GNU assembler syntax). Results go in `x0`. |
| `ember/runtime/ember_rt.c` | C `main`, panics, arrays, I/O. |
| `ember/driver.py` | Runs the toolchain and manages temporary files. |
| `ember/cli.py` | Command-line interface. |

Code generation notes:

- User functions get the symbol `em_<name>`, so they can't collide with libc.
- Every call aligns `rsp` to 16 bytes, so C interop stays correct at any expression depth.
- Frame slots are zeroed in the prologue, so reads of unassigned memory are deterministic.
- `INT_MIN / -1` wraps to `INT_MIN`, the same result two's complement gives, instead of trapping.

## Performance

Code generation is deliberately simple: every intermediate value goes through the stack, and
there is no register allocation or optimization pass. On a recursive `fib(32)` benchmark,
the output runs roughly 10 times slower than `gcc -O1`. Improving this is the most obvious
next step.

## Not yet implemented

Structs and enums, `match`, strings, arrays of floats, exponent notation (`1e10`), generics, `Option`/`Result`,
ownership and automatic memory management, modules and imports, inline assembly, and an
`unsafe` pointer model. These are on the roadmap. The sample programs use only what the
current compiler supports.

## Development

```
python -m unittest discover -s tests -v
```

The tests cover the lexer, parser, entry-point rules, type errors, code generation, the CLI,
runtime panics, and every program in `examples/`. Programs are compiled, run, and their
output compared with `.out` files. The end-to-end tests are skipped if `nasm` or `cc` is missing. The AArch64 tests are skipped
unless an AArch64 compiler and either an ARM64 host or qemu-aarch64 are available.
CI runs the same command on every push.

## Related repos

- [tesseraOS](https://github.com/enderman-claude/tesseraOS): the OS that runs SHARD images built by this compiler.
- [shard](https://github.com/enderman-claude/shard): the packer and loader. `--target shard` uses `elfpack`, and `shardelf` runs the result on Linux.
- [ember-gfx](https://github.com/enderman-claude/ember-gfx): the 2D graphics stack for Ember programs (X11, Win32 and headless backends).

## License

MIT. See [LICENSE](LICENSE).
