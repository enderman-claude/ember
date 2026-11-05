"""Windows on ARM64 target tests (--target windows-arm64).

Compile-level tests run everywhere. Build tests cross-compile the window example with
aarch64-w64-mingw32-gcc (llvm-mingw) and check the PE image: machine type, GUI subsystem
and system DLL imports. Running the .exe needs an ARM64 Windows machine, so it is not run
here; the AArch64 code itself is run under qemu by test_arm64.py.
"""
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import arm64_windows_compiler, build, compile_to_asm  # noqa: E402
from ember.errors import CompileError                                    # noqa: E402

WINDOW_EXAMPLE = ROOT / "examples" / "windows" / "window_test.em"
ARM64_WIN_CC = arm64_windows_compiler()
HAVE_ARM64_MINGW = bool(shutil.which(ARM64_WIN_CC))
IMAGE_FILE_MACHINE_ARM64 = 0xAA64
IMAGE_SUBSYSTEM_WINDOWS_GUI = 2


def pe_info(path):
    """Returns (machine, subsystem, magic) from a PE image."""
    data = Path(path).read_bytes()
    assert data[:2] == b"MZ", "not an MZ image"
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0", "missing PE signature"
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    subsystem = struct.unpack_from("<H", data, opt + 68)[0]  # PE32+ layout
    return machine, subsystem, magic


class WindowsArm64Compile(unittest.TestCase):
    def test_asm_has_no_elf_only_directives(self):
        asm = compile_to_asm(WINDOW_EXAMPLE.read_text(), "windows-arm64")
        self.assertNotIn(".note.GNU-stack", asm)
        self.assertIn(".globl em_main", asm)

    def test_linux_arm64_asm_keeps_the_gnu_stack_note(self):
        asm = compile_to_asm("def main():\n    print(1)\n", "linux-arm64")
        self.assertIn(".note.GNU-stack", asm)

    def test_large_constants_use_movz_movk(self):
        # clang's assembler rejects `mov x0, #imm` for values that are not logical
        # immediates (e.g. the colour 0x101020), so constants must use movz/movk.
        asm = compile_to_asm("def main():\n    print(1054760)\n", "windows-arm64")
        self.assertNotIn("mov x0, #1054760", asm)
        self.assertIn("movz x0, #6184, lsl #0", asm)
        self.assertIn("movk x0, #16, lsl #16", asm)

    def test_window_builtins_accepted_on_windows_arm64(self):
        compile_to_asm(WINDOW_EXAMPLE.read_text(), "windows-arm64")

    def test_window_builtins_rejected_on_linux_arm64(self):
        with self.assertRaises(CompileError) as cm:
            compile_to_asm(WINDOW_EXAMPLE.read_text(), "linux-arm64")
        self.assertIn("windows-arm64", str(cm.exception))


@unittest.skipUnless(HAVE_ARM64_MINGW,
                     f"{ARM64_WIN_CC} is required for Windows ARM64 builds "
                     "(llvm-mingw; set EMBER_ARM64_WIN_CC to override)")
class WindowsArm64Build(unittest.TestCase):
    def test_produces_arm64_gui_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = build(WINDOW_EXAMPLE, Path(tmp) / "window_test.exe", target="windows-arm64")
            machine, subsystem, magic = pe_info(exe)
            self.assertEqual(magic, 0x20B, "expected a PE32+ image")
            self.assertEqual(machine, IMAGE_FILE_MACHINE_ARM64)
            self.assertEqual(subsystem, IMAGE_SUBSYSTEM_WINDOWS_GUI)

    def test_imports_only_system_dlls(self):
        objdump = shutil.which("llvm-objdump")
        if objdump is None:
            self.skipTest("llvm-objdump not found")
        with tempfile.TemporaryDirectory() as tmp:
            exe = build(WINDOW_EXAMPLE, Path(tmp) / "window_test.exe", target="windows-arm64")
            out = subprocess.run([objdump, "-p", str(exe)], capture_output=True, text=True).stdout
            dlls = [line.split("DLL Name:")[1].strip() for line in out.splitlines()
                    if "DLL Name:" in line]
            self.assertTrue(dlls, "no imports found")
            for dll in dlls:
                self.assertTrue(dll.lower().endswith(".dll") and "/" not in dll and "\\" not in dll,
                                f"unexpected import {dll}")


if __name__ == "__main__":
    unittest.main()
