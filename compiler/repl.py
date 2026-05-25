"""Million interactive REPL with optional JIT execution."""

from __future__ import annotations

import sys
from pathlib import Path

from compiler import __version__
from compiler.compile import (
    compile_million,
    PROJECT_ROOT,
    parse_program,
    llvmlite_available as _check_llvm,
)


def _jit_run(llvm_ir: str, fn_name: str = "main") -> int:
    """JIT-compile and run LLVM IR, return main() exit code."""
    import llvmlite.binding as llvm

    llvm.initialize()
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()

    mod = llvm.parse_assembly(llvm_ir)
    mod.verify()

    target = llvm.Target.from_default_triple()
    tm = target.create_target_machine()
    engine = llvm.create_mcjit_compiler(mod, tm)
    engine.finalize_object()

    func_ptr = engine.get_function_address(fn_name)
    from ctypes import CFUNCTYPE, c_int

    cfunc = CFUNCTYPE(c_int)(func_ptr)
    return cfunc()


class REPL:
    def __init__(self):
        self.history: list[str] = []
        self.has_llvm = _check_llvm()

    def run(self):
        print(f"Million REPL v{__version__}")
        print(f"LLVM JIT: {'enabled' if self.has_llvm else 'disabled (pip install llvmlite)'}")
        print("Type code (end with blank line), or :help, :quit")
        print()

        while True:
            try:
                code = self._read_input()
                if code is None:
                    break
                if not code.strip():
                    continue
                if code.startswith(":"):
                    self._handle_command(code)
                    continue

                self.history.append(code)
                self._eval(code)
            except KeyboardInterrupt:
                print("\n(interrupted)")
                continue
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")

    def _read_input(self) -> str | None:
        lines = []
        print(">>> ", end="", flush=True)
        first = sys.stdin.readline()
        if not first:
            return None
        lines.append(first.rstrip("\n"))

        while True:
            print("... ", end="", flush=True)
            line = sys.stdin.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if not line and lines and lines[-1] == "":
                break
            lines.append(line)

        result = "\n".join(lines).strip()
        return result if result else None

    def _handle_command(self, cmd: str):
        cmd = cmd.strip().lower()
        if cmd in (":quit", ":exit", ":q"):
            print("Bye!")
            sys.exit(0)
        elif cmd == ":help":
            print("Commands:")
            print("  :quit  - exit REPL")
            print("  :help  - this help")
            print("  :hist  - show history")
            print("  :llvm  - toggle LLVM backend")
        elif cmd == ":hist":
            for i, h in enumerate(self.history[-20:], 1):
                print(f"  {i}: {h[:80]}...")
        elif cmd == ":llvm":
            self.has_llvm = not self.has_llvm
            print(f"LLVM JIT: {'enabled' if self.has_llvm else 'disabled'}")

    def _eval(self, code: str):
        source_path = PROJECT_ROOT / ".repl_tmp.million"
        source_path.write_text(code, encoding="utf-8")

        try:
            if self.has_llvm:
                llvm_ir = compile_million(
                    source_path, backend="llvm", search_paths=[PROJECT_ROOT / "stdlib"]
                )
                print(f"LLVM IR generated ({len(llvm_ir)} bytes)")
                result = _jit_run(llvm_ir)
                print(f"Exit code: {result}")
            else:
                c_code = compile_million(
                    source_path, backend="c", search_paths=[PROJECT_ROOT / "stdlib"]
                )
                print(c_code[:2000])
                if len(c_code) > 2000:
                    print(f"... ({len(c_code)} bytes total)")
        finally:
            if source_path.exists():
                source_path.unlink()


def main():
    REPL().run()


if __name__ == "__main__":
    main()
