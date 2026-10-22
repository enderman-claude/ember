"""Cross-compiles the window example to a Windows executable and checks its PE image.

Running the window itself needs a Windows machine (or Wine), so these tests check the
build output only: it's a 64-bit GUI executable that imports only system DLLs.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ember.driver import build  # noqa: E402

HAVE_MINGW = bool(shutil.which("nasm") and shutil.which("x86_64-w64-mingw32-gcc")
                  and shutil.which("x86_64-w64-mingw32-objdump"))


@unittest.skipUnless(HAVE_MINGW, "nasm and x86_64-w64-mingw32-gcc are required for Windows builds")
class WindowsBuild(unittest.TestCase):
    def build_window_example(self, tmp):
        return build(ROOT / "examples" / "windows" / "window_test.em",
                     Path(tmp) / "window_test.exe", target="windows")

    def test_produces_64bit_gui_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = self.build_window_example(tmp)
            self.assertEqual(exe.read_bytes()[:2], b"MZ")
            out = subprocess.run(["x86_64-w64-mingw32-objdump", "-p", str(exe)],
                                 capture_output=True, text=True).stdout
            self.assertIn("PE32+", subprocess.run(["file", "-b", str(exe)],
                                                  capture_output=True, text=True).stdout)
            self.assertIn("Windows GUI", out)

    def test_imports_only_system_dlls(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = self.build_window_example(tmp)
            out = subprocess.run(["x86_64-w64-mingw32-objdump", "-p", str(exe)],
                                 capture_output=True, text=True).stdout
            dlls = {line.split("DLL Name:")[1].strip().lower()
                    for line in out.splitlines() if "DLL Name:" in line}
            self.assertTrue({"user32.dll", "gdi32.dll", "kernel32.dll"} <= dlls, dlls)
            self.assertFalse(any("libgcc" in d or "libwinpthread" in d for d in dlls), dlls)


if __name__ == "__main__":
    unittest.main()
