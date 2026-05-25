"""Generate C code from neuron dynamics AST assignments."""

from __future__ import annotations

from compiler.parser.ast import Assignment, Call, Identifier, Literal
from compiler.ir.million_ir import MIRNeuron


class DynamicsCodegen:
    """Translate dynamics { ... } assignments into C statements."""

    def __init__(self, neuron: MIRNeuron):
        self.neuron = neuron
        self.nucleus_size = neuron.nucleus_size
        self.archive_levels = neuron.archive_levels
        self.vars: dict[str, dict] = {}
        self.lines: list[str] = []
        self.allocs: list[str] = []
        self._tmp = 0

    def _new_tmp(self) -> str:
        self._tmp += 1
        return f"dyn_tmp_{self._tmp}"

    def _size_for_ident(self, name: str) -> int | str:
        if name == "nucleus":
            return self.nucleus_size
        if name in self.vars:
            return self.vars[name]["size"]
        return self.nucleus_size

    def _ptr_for_ident(self, name: str) -> str:
        if name == "nucleus":
            return "n->nucleus"
        if name in self.vars:
            return self.vars[name]["ptr"]
        return "n->nucleus"

    def _emit_unfold(self, in_ptr: str, in_size: int | str, level: int) -> tuple[str, str]:
        out_ptr = self._new_tmp()
        if isinstance(in_size, int):
            out_size = in_size * self.archive_levels
        else:
            out_size = f"({in_size} * {self.archive_levels})"
        self.allocs.append(
            f"float {out_ptr}[{out_size}];"
        )
        self.lines.append(
            f"archive_unfold({in_ptr}, {in_size}, {out_ptr}, {out_size}, {level});"
        )
        return out_ptr, str(out_size) if isinstance(out_size, int) else out_size

    def _emit_compress(self, in_ptr: str, in_size: int | str, out_size: int | None = None) -> tuple[str, int]:
        target = out_size or self.nucleus_size
        if isinstance(in_size, int) and in_size == target:
            out_ptr = in_ptr
        elif isinstance(in_size, str):
            out_ptr = f"compressed_{self.neuron.name}"
            self.lines.append(
                f"float {out_ptr}[{target}];"
            )
            self.lines.append(
                f"archive_compress({in_ptr}, {in_size}, {out_ptr}, {target});"
            )
        else:
            out_ptr = f"compressed_{self.neuron.name}"
            self.lines.append(f"float {out_ptr}[{target}];")
            self.lines.append(
                f"archive_compress({in_ptr}, {in_size}, {out_ptr}, {target});"
            )
        return out_ptr, target

    def _gen_call(self, call: Call) -> tuple[str, int | str]:
        name = call.name
        args = call.args

        if name == "unfold" and len(args) >= 2:
            src = args[0]
            level = 1
            if isinstance(args[1], Literal) and isinstance(args[1].value, (int, float)):
                level = int(args[1].value)
            if isinstance(src, Identifier):
                in_ptr = self._ptr_for_ident(src.name)
                in_size = self._size_for_ident(src.name)
            else:
                in_ptr, in_size = self._gen_expr(src)
            return self._emit_unfold(in_ptr, in_size, level)

        if name == "compress" and len(args) >= 1:
            src = args[0]
            if isinstance(src, Call) and src.name == "unfold":
                ptr, size = self._gen_call(src)
                return self._emit_compress(ptr, size)
            if isinstance(src, Identifier):
                in_ptr = self._ptr_for_ident(src.name)
                in_size = self._size_for_ident(src.name)
            else:
                in_ptr, in_size = self._gen_expr(src)
            return self._emit_compress(in_ptr, in_size)

        if name == "compress" and len(args) == 1:
            return self._gen_call(Call(name="compress", args=[args[0]]))

        return self._emit_compress("n->nucleus", self.nucleus_size)

    def _gen_expr(self, node) -> tuple[str, int | str]:
        if isinstance(node, Call):
            return self._gen_call(node)
        if isinstance(node, Identifier):
            ptr = self._ptr_for_ident(node.name)
            size = self._size_for_ident(node.name)
            return ptr, size
        return "n->nucleus", self.nucleus_size

    def _malloc_vars(self) -> list[str]:
        return []

    def generate(self) -> tuple[list[str], list[str], str | None, list[str]]:
        """
        Returns (alloc_lines, body_lines, compressed_var, malloc_var_names).
        """
        if not self.neuron.dynamics:
            return [], [], None, []

        output_var = None
        for stmt in self.neuron.dynamics:
            if not isinstance(stmt, Assignment):
                continue
            target = stmt.target
            if isinstance(stmt.value, Call):
                ptr, size = self._gen_call(stmt.value)
                self.vars[target] = {"ptr": ptr, "size": size}
                if target == "output":
                    output_var = ptr
            elif isinstance(stmt.value, Identifier):
                ptr = self._ptr_for_ident(stmt.value.name)
                size = self._size_for_ident(stmt.value.name)
                self.vars[target] = {"ptr": ptr, "size": size}
                if target == "output":
                    output_var = ptr

        compressed = output_var or f"compressed_{self.neuron.name}"
        if compressed not in [v["ptr"] for v in self.vars.values()] and not any(
            compressed in line for line in self.lines
        ):
            ptr, _ = self._emit_compress("n->nucleus", self.nucleus_size)
            compressed = ptr

        return self.allocs, self.lines, compressed, self._malloc_vars()
