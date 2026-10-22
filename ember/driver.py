"""Ties the pipeline together: source -> tokens -> AST -> checked AST -> asm -> executable."""
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .parser import parse
from .checker import check
from .codegen import generate
from .codegen_arm64 import generate as generate_arm64

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ember_rt.c"
TARGETS = ("linux", "windows", "linux-arm64")


def compile_to_asm(src: str, target: str = "linux") -> str:
    """Run the front end and code generator. Raises CompileError on bad source."""
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}")
    prog = parse(src)
    check(prog, target)
    if target == "linux-arm64":
        return generate_arm64(prog)
    return generate(prog, target)


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{proc.stderr.strip()}")


def _require(*tools):
    for tool in tools:
        if shutil.which(tool) is None:
            raise RuntimeError(f"required tool {tool!r} not found on PATH")


def arm64_compiler() -> str:
    """C compiler that builds and links AArch64 Linux code.

    On an ARM64 host this is the native cc. Elsewhere it is the GNU cross compiler, unless
    EMBER_ARM64_CC names another one.
    """
    override = os.environ.get("EMBER_ARM64_CC")
    if override:
        return override
    if platform.machine().lower() in ("aarch64", "arm64"):
        return "cc"
    return "aarch64-linux-gnu-gcc"


def build(src_path, out_path, target: str = "linux", link=()) -> Path:
    """Compile a .em file to an executable at out_path.

    target="linux" produces an ELF executable with nasm and cc.
    target="windows" produces a static Windows GUI executable (.exe) with nasm and
    x86_64-w64-mingw32-gcc.
    target="linux-arm64" produces an AArch64 ELF executable. It needs no NASM: the generated
    GNU assembly is assembled by the cross (or native) gcc, which also links the runtime.

    link is a list of extra C sources or objects (they supply `extern def` functions) and
    compiler or linker flags, such as "-lX11", "-Idir" or "-DNAME=1".
    """
    asm = compile_to_asm(Path(src_path).read_text(), target)
    # Items starting with "-" are compiler or linker flags (e.g. -lX11, -I dir, -DNAME);
    # everything else is a C source or object file.
    sources = [str(x) for x in link if not str(x).startswith("-")]
    flags = [str(x) for x in link if str(x).startswith("-")]
    out = Path(out_path)

    if target == "linux-arm64":
        cc = arm64_compiler()
        _require(cc)
        with tempfile.TemporaryDirectory() as tmp:
            asm_file = Path(tmp) / "prog.s"
            asm_file.write_text(asm)
            _run([cc, "-O1", "-o", str(out), str(RUNTIME), str(asm_file), *sources, *flags, "-lm"])
        return out

    if target == "windows":
        cc, obj_format = "x86_64-w64-mingw32-gcc", "win64"
    else:
        cc, obj_format = "cc", "elf64"
    _require("nasm", cc)

    with tempfile.TemporaryDirectory() as tmp:
        asm_file = Path(tmp) / "prog.asm"
        obj_file = Path(tmp) / "prog.obj"
        asm_file.write_text(asm)
        _run(["nasm", "-f", obj_format, "-Werror", "-o", str(obj_file), str(asm_file)])
        if target == "windows":
            # -mwindows: GUI subsystem, no console. -static: no MinGW DLLs needed at runtime.
            _run([cc, "-O1", "-mwindows", "-static", "-o", str(out), str(RUNTIME), str(obj_file),
                  *sources, *flags, "-luser32", "-lgdi32"])
        else:
            _run([cc, "-O1", "-o", str(out), str(RUNTIME), str(obj_file), *sources, *flags, "-lm"])
    return out
