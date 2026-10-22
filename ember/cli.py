"""Command-line interface: `ember build|run|check|emit-asm FILE`."""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from .driver import build, compile_to_asm
from .errors import CompileError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ember", description="The Ember compiler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="compile to a native executable")
    p_build.add_argument("file")
    p_build.add_argument("-o", "--output", help="output path (default: source name without .em)")

    p_run = sub.add_parser("run", help="compile and run")
    p_run.add_argument("file")

    p_check = sub.add_parser("check", help="type-check without producing output")
    p_check.add_argument("file")

    p_asm = sub.add_parser("emit-asm", help="print the generated NASM assembly")
    p_asm.add_argument("file")

    args = parser.parse_args(argv)
    src_path = Path(args.file)

    try:
        if args.cmd == "check":
            compile_to_asm(src_path.read_text())
            print("ok")
        elif args.cmd == "emit-asm":
            print(compile_to_asm(src_path.read_text()), end="")
        elif args.cmd == "build":
            out = Path(args.output) if args.output else src_path.with_suffix("")
            build(src_path, out)
            print(f"built {out}")
        elif args.cmd == "run":
            with tempfile.TemporaryDirectory() as tmp:
                exe = build(src_path, Path(tmp) / "prog")
                return subprocess.run([str(exe)]).returncode
    except CompileError as err:
        print(f"{args.file}: error: {err}", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    return 0
