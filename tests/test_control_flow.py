"""Tests for control flow parsing and codegen."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.compile import compile_million, PROJECT_ROOT

def test_if_in_dynamics():
    c = compile_million(PROJECT_ROOT / "examples" / "chat_neuron.million", backend="c")
    assert "if (" in c
    print("  [ok] test_if_in_dynamics")

def test_cgen_has_control_flow():
    c = compile_million(PROJECT_ROOT / "examples" / "types_demo.million", backend="c")
    assert "return" in c
    print("  [ok] test_cgen_has_control_flow")

def test_while():
    src = """
neuron N {
    nucleus: state[4]
    membrane { potential: 0.0 threshold: 1.0 refractory: 0 }
    dynamics {
        x = 0
        while x < 5 {
            x = x + 1
        }
        output = x
    }
}
region R { neurons: N[1] }
infer R on z { output -> w }
"""
    from compiler.compile import compile_million, Path
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".million"))
    try:
        tmp.write_text(src)
        c = compile_million(tmp, backend="c")
        assert "while (x < 5)" in c or "while (" in c
        print("  [ok] test_while")
    finally:
        if tmp.exists(): tmp.unlink()

if __name__ == "__main__":
    print("Running control flow tests...")
    test_if_in_dynamics()
    test_cgen_has_control_flow()
    test_while()
    print("All control flow tests passed!")
