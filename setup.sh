#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Million Language Setup ==="
python3 --version
echo ""
echo "Running tests..."
python3 tests/run_all.py
echo ""
echo "Compiling chat_neuron.million -> examples/chat_neuron.c"
python3 -m compiler.main examples/chat_neuron.million examples/chat_neuron.c -q
echo ""
if command -v gcc >/dev/null 2>&1; then
  echo "Building executable..."
  gcc examples/chat_neuron.c -o examples/chat_neuron -lm -Wall
  echo "Run: ./examples/chat_neuron"
else
  echo "Install gcc to build the C output."
fi
echo "Setup complete."
