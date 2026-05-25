# Million Language

**Million** — предметно-орієнтована мова для brain-inspired / нейроморфних обчислень. Описуєте нейрони, регіони, навчання та інференс; компілятор транспілює програму в portable **C**.

Версія: **0.3.0**

## Можливості

- Повний пайплайн: **Lexer → Parser → MIR → C / LLVM codegen**
- **Event-driven runtime**: нейрони обчислюються лише при спайках (черга подій + CSR синапси)
- **Backprop через archive**: `archive_unfold_grad`, гібридне навчання (gradient + STDP)
- **LLVM backend** (опційно): `pip install llvmlite`, `--backend llvm`
- Нейрони з `archive{state[N], levels}` або `state[N]`
- Динаміка: `unfold`, `compress` (з AST, не хардкод)
- Регіони, `connect` з ваговою матрицею та STDP/hebbian
- `data` + завантаження файлу датасету при `train`
- `use "path.million"` — імпорт stdlib та модулів
- Інтерактивний REPL у згенерованому `main()`
- Тести та CI (GitHub Actions)

## Швидкий старт

### Вимоги

- Python 3.9+
- GCC / MinGW / MSVC (для збірки згенерованого C)

### Компіляція

```bash
# з кореня репозиторію
python -m compiler.main examples/chat_neuron.million examples/chat_neuron.c

# або після pip install -e .
million examples/chat_neuron.million -q
million examples/spiking_chat.million --backend c
million examples/minimal.million --backend llvm   # потрібен llvmlite
```

### Збірка C (Windows, MinGW)

```powershell
gcc examples/chat_neuron.c -o examples/chat_neuron.exe -lm
.\examples\chat_neuron.exe
```

### Збірка C (Linux / macOS)

```bash
gcc examples/chat_neuron.c -o examples/chat_neuron -lm
./examples/chat_neuron
```

### Тести

```bash
python tests/run_all.py
```

### Setup-скрипти

```powershell
.\setup.ps1      # Windows
```

```bash
./setup.sh       # Linux / macOS
```

## Синтаксис (скорочено)

```million
neuron DNA {
    nucleus: archive{state[16], 3}
    membrane {
        potential: 0.0
        threshold: adaptive
        refractory: 1
    }
    dynamics {
        level1 = unfold(nucleus, 1)
        level2 = unfold(level1, 2)
        output = compress(level2)
    }
}

region Cortex {
    neurons: DNA[100]
    connect self -> self: hierarchical {
        branching: 4
        sparsity: 0.01
        plasticity: STDP
    }
}

data ChatData {
    source: "conversations.txt"
    shape: [16, 100]
}

train Cortex on ChatData {
    epochs: 10
    rule: hebbian
    mode: hybrid
    learning_rate: 0.01
    stdp_lr: 0.005
}

infer Cortex on input {
    output -> result
}
```

### Імпорт stdlib

```million
use "stdlib/neuron_base.million"
```

## Структура проєкту

```
compiler/          # Компілятор Python
  lexer/           # Лексичний аналіз
  parser/          # AST
  ir/              # MIR (middle IR)
  codegen/         # Генерація C + dynamics
  compile.py       # Драйвер, resolve imports
examples/          # Приклади .million + conversations.txt
stdlib/            # Бібліотека типів нейронів і правил
tests/             # Юніт- та e2e-тести
```

## Приклади

| Файл | Опис |
|------|------|
| `examples/chat_neuron.million` | Повний демо: train + інтерактивний чат |
| `examples/minimal.million` | Мінімальна програма без датасету |
| `examples/spiking_chat.million` | Event-driven чат + hybrid train |
| `stdlib/neuron_base.million` | LIF, Sensory, Motor, Memory |
| `stdlib/learning_rules.million` | hebbian, stdp, oja, reinforce (декларативно) |

## CLI

```
million [-h] [-V] [-q] [--backend auto|c|llvm] input [output]
```

### Backends

| Backend | Опис |
|---------|------|
| `c` (default без llvmlite) | Portable C, event loop, backprop |
| `llvm` | LLVM IR + verify (+ optional O3 passes) |
| `auto` | LLVM якщо встановлено `llvmlite`, інакше C |

## Ліцензія

MIT — див. [LICENSE](LICENSE).
