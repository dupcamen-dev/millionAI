.PHONY: test compile build clean

PYTHON ?= python

test:
	$(PYTHON) tests/run_all.py

compile:
	$(PYTHON) -m compiler.main examples/chat_neuron.million examples/chat_neuron.c -q
	$(PYTHON) -m compiler.main examples/minimal.million examples/minimal.c -q

build: compile
	gcc examples/chat_neuron.c -o examples/chat_neuron -lm -Wall -Wextra

clean:
	rm -f examples/*.c examples/chat_neuron examples/minimal
