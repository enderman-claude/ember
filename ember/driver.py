"""Ties the pipeline together: source -> tokens -> AST -> checked AST -> asm -> executable."""
import shutil
import subprocess
import tempfile
from pathlib import Path

from .parser import parse
from .checker import check
from .codegen import generate

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ember_rt.c"


def compile_to_asm(src: str) -> str:
    """Run the front end and code generator. Raises CompileError on bad source."""
    prog = parse(src)
    check(prog)
    return generate(prog)


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed:\n{proc.stderr.strip()}")


def build(src_path, out_path) -> Path:
    """Compile a .em file to a native executable at out_path."""
    for tool in ("nasm", "cc"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"required tool {tool!r} not found on PATH")
    asm = compile_to_asm(Path(src_path).read_text())
    out = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        asm_file = Path(tmp) / "prog.asm"
        obj_file = Path(tmp) / "prog.o"
        asm_file.write_text(asm)
        _run(["nasm", "-f", "elf64", "-Werror", "-o", str(obj_file), str(asm_file)])
        _run(["cc", "-O1", "-o", str(out), str(RUNTIME), str(obj_file)])
    return out
