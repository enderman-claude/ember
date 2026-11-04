# Changelog

## Unreleased

### Added
- Floating-point types `f32` (single) and `f64` (double), with IEEE 754 arithmetic and
  comparisons. Decimal literals are `f64` (`1.5`); `1.5f32` is `f32`.
- `bigfloat`: an exact rational number of any size, written with the suffix `big` (`1.5big`,
  `2big`). Values are kept in lowest terms, so `100big / 3big` stays 100/3.
- Conversion functions `f32(x)`, `f64(x)`, `bigfloat(x)` and `i64(x)`. Numbers never convert
  implicitly.
- Printing for all numeric types. Floats print the shortest decimal that reads back as the same
  value (same rules as Python's `repr`); bigfloats print exactly when the decimal ends, and
  otherwise with 40 digits and `...`.
- `ember/runtime/ember_num.h`: the numeric runtime, shared by the Linux, Windows and SHARD
  runtimes. It has no libc dependency.
- `ember/floats.py`: exact decimal-to-float conversion for literals (correct rounding, ties to even).
- Panics for a bigfloat division by zero, a float that does not fit in `i64`, and a conversion
  of NaN or infinity to `bigfloat`.
- Examples `examples/floats.em` and `examples/bigfloat.em`. `tests/test_floats.py` and
  `tests/num_test.c` (checked against expectations from `tests/gen_num_cases.py`).

### Changed
- `extern def` takes and returns only `i64`, `bool` and `[i64]`. Floats are not passed in SSE
  registers, so a C function cannot receive them.
- Integer and float constants are loaded with `movz`/`movk` on AArch64. Some 64-bit constants
  cannot be moved with one `mov` (for example `0x123456789ABC`, or the bit pattern of `1.0 / 3.0`),
  so programs using them previously failed to assemble.

## 0.6.0

### Added
- `--target shard`: builds a SHARD image (tesseraOS native format) through `elfpack`
- `ember/runtime/ember_rt_shard.c`: freestanding runtime that makes system calls directly, with no libc
- `tests/test_shard.py`: runs SHARD builds through `shardelf` and compares output with the Linux build
- `--target linux-arm64`: builds an AArch64 (ARM64) Linux executable. The new backend is
  `ember/codegen_arm64.py`, using AAPCS64 and GNU assembler syntax. It needs no NASM: gcc
  assembles and links the output.
- `EMBER_ARM64_CC` overrides the compiler used for AArch64 builds. By default the native `cc`
  is used on ARM64 hosts and `aarch64-linux-gnu-gcc` elsewhere.
- `tests/test_arm64.py`: compile-level checks, plus every example run as an AArch64 executable
  under qemu-user or natively on ARM64

### Changed
- CI installs the AArch64 cross compiler and qemu-user, so the AArch64 tests run on every push

## 0.5.0

### Added
- `extern def name(params) -> type`: declares a C function that Ember programs can call.
  Arguments follow the platform calling convention, so C code can implement them directly.
- `--link ITEM` on `build` and `run`: adds a C source, an object file, or a compiler or
  linker flag such as `-lX11` or `-Idir`
- `examples/ffi/`: an Ember program calling C functions
- Hexadecimal literals (`0xFF0000`) and `_` digit separators (`1_000_000`)

## 0.4.0

### Added
- `--target windows`: builds a static 64-bit Windows GUI executable with MinGW-w64
- Win64 calling convention for Windows builds (argument registers and shadow space)
- Window builtins `window_open`, `window_present`, `window_closed` (Windows target only)
- `examples/windows/window_test.em`: animated gradient in a real window
- Windows PE image tests and a strict-warnings compile of the Windows runtime

### Changed
- Functions take at most four parameters, so every target can pass them in registers
- Panics on Windows show a message box, since GUI programs have no console

## 0.3.0

### Added
- `put_byte` builtin for writing raw binary to stdout
- `examples/graphics/graphics_test.em`: renders a 320x240 framebuffer and writes a 24-bit BMP
- Test that checks the BMP header and sample pixels

## 0.2.0

### Added
- Arrays: `[i64]` type, `alloc`, `free`, `len`, indexing and index assignment, and array literals
- Bounds-checked element access
- `for x in range(stop)` and `for x in range(start, stop)`
- `break` and `continue`
- `print` accepts `bool` as well as `i64`
- `read_int` and `input_ended` builtins for reading stdin
- Runtime panics for division by zero, out-of-bounds indexing, and failed allocation, all exiting with status 101
- `ember run` passes stdin and the program's exit status through
- End-to-end tests that compile and run every program in `examples/`

### Fixed
- Binding a value of type `unit` (for example `x = print(1)`) is now a compile error
- Division by zero no longer crashes with SIGFPE
- `INT_MIN / -1` no longer traps
- Windows (CRLF) line endings are accepted

### Changed
- Generated code preserves the 16-byte stack alignment at every call site
- Frame slots are zeroed in function prologues

## 0.1.0

- Initial release: indentation-aware front end, type checker, x86-64 codegen, C runtime,
  and a CLI with `build`, `run`, `check`, and `emit-asm`
