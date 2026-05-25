"""Compilation driver: parse, resolve imports, build IR, generate code."""

from __future__ import annotations

from pathlib import Path

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.parser.ast import Program, UseStmt
from compiler.ir.million_ir import IRBuilder
from compiler.codegen import CCodeGen

__all__ = [
    "compile_million",
    "parse_program",
    "PROJECT_ROOT",
    "llvmlite_available",
    "get_codegen",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _project_root()


def llvmlite_available() -> bool:
    from compiler.codegen.llvm_codegen import llvmlite_available as _check

    return _check()


def get_codegen(mir, source_dir: Path, backend: str = "auto"):
    """Return codegen instance for backend: c, llvm, or auto."""
    use_llvm = backend == "llvm" or (backend == "auto" and llvmlite_available())
    if use_llvm:
        try:
            from compiler.codegen.llvm_codegen import LLVMCodeGen

            gen = LLVMCodeGen(mir)
            gen._ensure_llvm()
            return gen, "llvm"
        except (ImportError, RuntimeError) as exc:
            if backend == "llvm":
                raise RuntimeError(
                    "LLVM backend failed (install llvmlite: pip install llvmlite)"
                ) from exc
    return CCodeGen(mir, source_dir=source_dir), "c"


def _resolve_import_path(
    import_path: str, base_dir: Path, search_paths: list[Path]
) -> Path:
    candidates: list[Path] = []
    raw = Path(import_path)
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(base_dir / raw)
        for sp in search_paths:
            candidates.append(sp / raw)
        candidates.append(PROJECT_ROOT / raw)
        if not str(raw).endswith(".million"):
            for c in list(candidates):
                candidates.append(c.with_suffix(".million"))

    seen: set[Path] = set()
    for path in candidates:
        p = path.resolve()
        if p in seen:
            continue
        seen.add(p)
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"Cannot resolve import '{import_path}' (searched from {base_dir})"
    )


def parse_program(
    source_path: str | Path,
    *,
    search_paths: list[Path] | None = None,
    _loaded: set[Path] | None = None,
) -> Program:
    """Parse a .million file and recursively resolve ``use`` imports."""
    source_path = Path(source_path).resolve()
    if _loaded is None:
        _loaded = set()
    if source_path in _loaded:
        return Program(declarations=[])
    _loaded.add(source_path)

    if search_paths is None:
        search_paths = [PROJECT_ROOT, PROJECT_ROOT / "stdlib", PROJECT_ROOT / "examples"]

    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    lexer = Lexer(source)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()

    merged: list = []
    base_dir = source_path.parent

    for decl in ast.declarations:
        if isinstance(decl, UseStmt):
            imp = _resolve_import_path(decl.path, base_dir, search_paths)
            sub = parse_program(imp, search_paths=search_paths, _loaded=_loaded)
            merged.extend(sub.declarations)
        else:
            merged.append(decl)

    return Program(declarations=merged)


def compile_million(
    source_path: str | Path,
    output_path: str | Path | None = None,
    *,
    search_paths: list[Path] | None = None,
    backend: str = "auto",
    **kwargs,
) -> str:
    """Compile Million source. Returns generated source (C or LLVM IR)."""
    source_path = Path(source_path)
    ast = parse_program(source_path, search_paths=search_paths)
    quantization = kwargs.get("quantization", "f32")
    learning_mode = kwargs.get("mode", "hybrid")
    builder = IRBuilder()
    mir = builder.build(ast, quantization=quantization, learning_mode=learning_mode)
    codegen, kind = get_codegen(
        mir, source_dir=source_path.resolve().parent, backend=backend
    )
    code = codegen.generate()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)

    return code
