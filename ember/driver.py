"""Ties the pipeline together: source -> tokens -> AST -> checked AST -> asm -> executable."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .parser import parse
from .checker import check
from .codegen import generate
from .errors import CompileError

RUNTIME = Path(__file__).resolve().parent / "runtime" / "ember_rt.c"
SHARD_RUNTIME = Path(__file__).resolve().parent / "runtime" / "ember_rt_shard.c"
TARGETS = ("linux", "windows", "shard")


def compile_to_asm(src: str, target: str = "linux") -> str:
    """Run the front end and code generator. Raises CompileError on bad source."""
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}")
    prog = parse(src)
    if target == "shard":
        for f in prog.funcs:
            if f.body is None:
                raise CompileError(f.line, f"extern def {f.name}() is not available for --target shard "
                                           "(SHARD images cannot call C code)")
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


def _find_elfpack():
    """Locate the SHARD packer. EMBER_ELFPACK overrides the search on PATH."""
    path = os.environ.get("EMBER_ELFPACK") or shutil.which("elfpack")
    if not path:
        raise RuntimeError("elfpack not found: build it from https://github.com/enderman-claude/shard "
                           "(make build/elfpack) and put it on PATH or set EMBER_ELFPACK")
    return path


def build(src_path, out_path, target: str = "linux", link=()) -> Path:
    """Compile a .em file to an executable at out_path.

    target="linux" produces an ELF executable with nasm and cc.
    target="windows" produces a static Windows GUI executable (.exe) with nasm and
    x86_64-w64-mingw32-gcc.
    target="shard" produces a SHARD image (tesseraOS native format). It links a
    freestanding runtime into a static-pie ELF and packs it with elfpack.

    link is a list of extra C sources or objects (they supply `extern def` functions) and
    compiler or linker flags, such as "-lX11", "-Idir" or "-DNAME=1".
    """
    if target == "windows":
        cc, obj_format = "x86_64-w64-mingw32-gcc", "win64"
    else:
        cc, obj_format = "cc", "elf64"
    _require("nasm", cc)

    # Items starting with "-" are compiler or linker flags (e.g. -lX11, -I dir, -DNAME);
    # everything else is a C source or object file.
    sources = [str(x) for x in link if not str(x).startswith("-")]
    flags = [str(x) for x in link if str(x).startswith("-")]
    if target == "shard" and link:
        raise RuntimeError("--link is not supported for --target shard (SHARD images cannot call C code)")

    asm = compile_to_asm(Path(src_path).read_text(), target)
    out = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        asm_file = Path(tmp) / "prog.asm"
        obj_file = Path(tmp) / "prog.obj"
        asm_file.write_text(asm)
        _run(["nasm", "-f", obj_format, "-Werror", "-o", str(obj_file), str(asm_file)])
        if target == "shard":
            elfpack = _find_elfpack()
            elf_file = Path(tmp) / "prog.elf"
            # Static-pie with no libc: no DT_NEEDED and no undefined symbols, which SHARD
            # requires. Compiler builtins that would become memset/memcpy calls are disabled.
            _run([cc, "-O1", "-static-pie", "-nostdlib", "-ffreestanding", "-fno-builtin",
                  "-fno-stack-protector", "-fno-tree-loop-distribute-patterns",
                  "-o", str(elf_file), str(SHARD_RUNTIME), str(obj_file)])
            _run([elfpack, str(elf_file), str(out)])
        elif target == "windows":
            # -mwindows: GUI subsystem, no console. -static: no MinGW DLLs needed at runtime.
            _run([cc, "-O1", "-mwindows", "-static", "-o", str(out), str(RUNTIME), str(obj_file),
                  *sources, *flags, "-luser32", "-lgdi32"])
        else:
            _run([cc, "-O1", "-o", str(out), str(RUNTIME), str(obj_file), *sources, *flags, "-lm"])
    return out
