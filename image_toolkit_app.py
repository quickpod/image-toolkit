#!/usr/bin/env python3
r"""Image Toolkit unified entry point (this is what gets built into ImageToolkit.exe).

  ImageToolkit.exe                 -> launch the GUI editor
  ImageToolkit.exe <command> ...   -> run the CLI (same as `python -m imgtoolkit ...`)

100% open source, fully offline. Nothing is uploaded anywhere.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Single-instance marker: the installer's AppMutex checks this to warn the
# user to close the app before install/uninstall. Harmless off Windows.
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.kernel32.CreateMutexW(None, False, "QuickOpen.ImageToolkit")
    except Exception:
        pass



def main():
    argv = sys.argv[1:]
    if argv:
        from imgtoolkit import __main__ as cli
        if hasattr(cli, "main"):
            try:
                return cli.main(argv)
            except TypeError:
                sys.argv = ["imgtoolkit", *argv]
                return cli.main()
        sys.argv = ["imgtoolkit", *argv]
        import runpy
        runpy.run_module("imgtoolkit", run_name="__main__")
        return 0
    from imgtoolkit import gui
    return gui.main() or 0


if __name__ == "__main__":
    sys.exit(main() or 0)
