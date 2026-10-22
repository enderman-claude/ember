"""Ties the pipeline together: source -> tokens -> AST -> checked AST -> asm -> executable."""
import shutil
import subprocess
import tempfile
from pathlib import Path

from .parser import parse
from .checker import check
from .codegen import generate

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ember_rt.c"
TARGETS = ("linux", "windows")


def compile_to_asm(src: str, target: str = "linux") -> str:
    """Run the front end and code generator. Raises CompileError on bad source."""
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}")
    prog = parse(src)
    check(prog, target)
    return generate(prog, target)


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{proc.stderr.strip()}")


def _require(*tools):
    for tool in tools:
        if shutil.which(tool) is None:
            raise RuntimeError(f"required tool {tool!r} not found on PATH")


def build(src_path, out_path, target: str = "linux") -> Path:
    """Compile a .em file to an executable at out_path.

    target="linux" produces an ELF executable with nasm and cc.
    target="windows" produces a static Windows GUI executable (.exe) with nasm and
    x86_64-w64-mingw32-gcc.
    """
    if target == "windows":
        cc, obj_format = "x86_64-w64-mingw32-gcc", "win64"
    else:
        cc, obj_format = "cc", "elf64"
    _require("nasm", cc)

    asm = compile_to_asm(Path(src_path).read_text(), target)
    out = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        asm_file = Path(tmp) / "prog.asm"
        obj_file = Path(tmp) / "prog.obj"
        asm_file.write_text(asm)
        _run(["nasm", "-f", obj_format, "-Werror", "-o", str(obj_file), str(asm_file)])
        if target == "windows":
            # -mwindows: GUI subsystem, no console. -static: no MinGW DLLs needed at runtime.
            _run([cc, "-O1", "-mwindows", "-static", "-o", str(out), str(RUNTIME), str(obj_file),
                  "-luser32", "-lgdi32"])
        else:
            _run([cc, "-O1", "-o", str(out), str(RUNTIME), str(obj_file)])
    return out
