"""Tests for Pattern Classifier neural network."""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, PROJECT_ROOT


def test_pattern_parses():
    from compiler.lexer import Lexer
    from compiler.parser import Parser
    path = PROJECT_ROOT / "examples" / "pattern_classifier.million"
    assert path.exists(), f"File not found: {path}"
    src = path.read_text(encoding="utf-8")
    parser = Parser(Lexer(src).tokenize())
    prog = parser.parse()
    names = [type(d).__name__ for d in prog.declarations]
    assert "NeuronDef" in names, f"No NeuronDef found in {names}"
    assert "RegionDef" in names, f"No RegionDef found in {names}"
    assert "DataDef" in names, f"No DataDef found in {names}"
    assert "TrainStmt" in names, f"No TrainStmt found in {names}"
    assert "InferStmt" in names, f"No InferStmt found in {names}"
    print("  [ok] test_pattern_parses")


def test_pattern_c_codegen():
    path = PROJECT_ROOT / "examples" / "pattern_classifier.million"
    c = compile_million(path, backend="c")
    assert "Neuron_PatternNeuron" in c, "Missing neuron struct"
    assert "train_Cortex" in c, "Missing train function"
    assert "infer_Cortex" in c, "Missing infer function"
    assert "archive_unfold" in c, "Missing archive_unfold"
    assert "apply_stdp" in c, "Missing STDP"
    assert "train_step_hybrid_PatternNeuron" in c, "Missing hybrid training"
    print("  [ok] test_pattern_c_codegen")


def test_pattern_llvm_codegen():
    from compiler.codegen.llvm_codegen import LLVMCodeGen, llvmlite_available
    if not llvmlite_available():
        print("  [skip] test_pattern_llvm_codegen (llvmlite not installed)")
        return
    path = PROJECT_ROOT / "examples" / "pattern_classifier.million"
    from compiler.compile import parse_program
    from compiler.ir.million_ir import IRBuilder
    ast = parse_program(path)
    mir = IRBuilder().build(ast)
    llvm = LLVMCodeGen(mir)
    ir = llvm.generate()
    assert "archive_unfold" in ir
    assert "archive_compress" in ir
    assert "train_step_hybrid" in ir or "process_PatternNeuron" in ir
    print("  [ok] test_pattern_llvm_codegen")


def test_pattern_has_archive():
    path = PROJECT_ROOT / "examples" / "pattern_classifier.million"
    c = compile_million(path, backend="c")
    assert "archive_unfold_grad" in c
    assert "archive_compress_grad" in c
    assert "bptt_backward_Cortex" in c
    print("  [ok] test_pattern_has_archive")


def test_pattern_can_train_on_hybrid_mode():
    from compiler.compile import parse_program
    from compiler.ir.million_ir import IRBuilder
    path = PROJECT_ROOT / "examples" / "pattern_classifier.million"
    mir = IRBuilder().build(parse_program(path))
    assert len(mir.train_stmts) == 1
    t = mir.train_stmts[0]
    assert t.mode == "hybrid"
    assert t.epochs == 30
    assert t.rule == "hebbian"
    assert abs(t.learning_rate - 0.001) < 1e-9
    print("  [ok] test_pattern_can_train_on_hybrid_mode")


if __name__ == "__main__":
    print("Pattern Classifier Tests:")
    test_pattern_parses()
    test_pattern_c_codegen()
    test_pattern_llvm_codegen()
    test_pattern_has_archive()
    test_pattern_can_train_on_hybrid_mode()
    print("All pattern tests passed!")
