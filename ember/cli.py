"""Command-line interface: `ember build|run|check|emit-asm FILE`."""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from .driver import TARGETS, build, compile_to_asm
from .errors import CompileError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ember", description="The Ember compiler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="compile to an executable")
    p_build.add_argument("file")
    p_build.add_argument("-o", "--output", help="output path (default: source name without .em, plus .exe on Windows)")
    p_build.add_argument("--target", choices=TARGETS, default="linux",
                         help="linux (x86-64 ELF), windows (.exe, GUI subsystem) or linux-arm64 (AArch64 ELF)")
    p_build.add_argument("--link", action="append", default=[], metavar="FILE",
                         help="C source, object or linker flag (e.g. -lm); repeatable")

    p_run = sub.add_parser("run", help="compile and run on this machine (Linux)")
    p_run.add_argument("file")
    p_run.add_argument("--link", action="append", default=[], metavar="FILE",
                       help="C source, object or linker flag (e.g. -lm); repeatable")

    p_check = sub.add_parser("check", help="type-check without producing output")
    p_check.add_argument("file")
    p_check.add_argument("--target", choices=TARGETS, default="linux")

    p_asm = sub.add_parser("emit-asm", help="print the generated NASM assembly")
    p_asm.add_argument("file")
    p_asm.add_argument("--target", choices=TARGETS, default="linux")

    args = parser.parse_args(argv)
    src_path = Path(args.file)

    try:
        if args.cmd == "check":
            compile_to_asm(src_path.read_text(), args.target)
            print("ok")
        elif args.cmd == "emit-asm":
            print(compile_to_asm(src_path.read_text(), args.target), end="")
        elif args.cmd == "build":
            default = src_path.with_suffix(".exe" if args.target == "windows" else "")
            out = Path(args.output) if args.output else default
            build(src_path, out, args.target, link=args.link)
            print(f"built {out}")
        elif args.cmd == "run":
            with tempfile.TemporaryDirectory() as tmp:
                exe = build(src_path, Path(tmp) / "prog", "linux", link=args.link)
                return subprocess.run([str(exe)]).returncode
    except CompileError as err:
        print(f"{args.file}: error: {err}", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    return 0
