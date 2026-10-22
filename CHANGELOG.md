# Changelog

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
