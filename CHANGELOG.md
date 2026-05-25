# Changelog

## 0.3.0

### Fixes (0.3.1)
- LLVM: `archive_unfold_grad` and `archive_compress_grad` (parity with C backprop)
- LLVM: real `archive_unfold`/`archive_compress` loops, `process_*`, `init_*`, `main`
- Memory: `goto process_cleanup` frees all dynamics `malloc` on refractory exit
- Hybrid target: `tanhf(input[i % ns])` via `bptt_backward_*` (not `output[i]`)
- BPTT: per-timestep nucleus checkpoints + backward pass over `BPTT_STEPS`

- **Event-driven runtime**: spike queue, sorted insertion, CSR synapses, `run_region_*`
- `process_*` returns `int` (fired or not); neurons run only on events
- `step_region_*` kept for backward compatibility (wraps event loop)
- **Backprop**: `archive_unfold_grad`, `archive_compress_grad`, `train_step_hybrid_*`
- Train supports `mode: hybrid`, `stdp_lr`
- **LLVM backend** (`--backend llvm`) via llvmlite with C fallback
- MIR: `MIRSpikeEvent`, `MIRSparseConnection`, `sparse_connections`
- Example: `examples/spiking_chat.million`
- Tests: event-driven, backprop, LLVM

## 0.2.0

- Added `use` imports and `compiler/compile.py` driver
- AST-driven dynamics codegen (`compiler/codegen/dynamics.py`)
- C codegen: dataset loading, hebbian/stdp training, region connectivity
- CLI with argparse (`-V`, `-q`)
- README, LICENSE (MIT), pyproject.toml, Makefile
- Sample `examples/conversations.txt` and `examples/minimal.million`
- GitHub Actions CI (Python tests + gcc build)
- Comparison operators (`>=`, `<=`, `==`, `!=`) in lexer/parser
- Expanded test suite (import, codegen)

## 0.1.0

- Initial compiler: lexer, parser, MIR, C codegen
- Chat neuron example
