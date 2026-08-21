# rfalloc build pipeline. Requires only Python 3.11+ and a C99 compiler.

PYTHON ?= python3
CC     ?= cc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -pedantic -O2

BUILD  := build
ARTIFACTS := $(BUILD)/rfalloc.sqlite $(BUILD)/rfalloc.json $(BUILD)/rfalloc.min.json $(BUILD)/rfalloc.bin

.PHONY: all data binary test test-python test-c test-swift clean lookup

all: data binary

## Parse the FCC source document into SQLite and JSON.
data:
	$(PYTHON) tools/build_db.py

## Emit the flat table used by the C and Swift readers.
binary: data
	$(PYTHON) tools/build_binary.py
	cp $(BUILD)/rfalloc.bin swift/RFAllocTests/rfalloc.bin

test: test-python test-c test-swift

## Structural invariants of the parse: no gaps, no overlaps, known frequencies.
test-python:
	$(PYTHON) tools/test_parser.py

test-c: binary
	$(CC) $(CFLAGS) -o $(BUILD)/test_rfalloc c/rfalloc.c c/test_rfalloc.c
	$(BUILD)/test_rfalloc $(BUILD)/rfalloc.bin

test-swift: binary
	swift test

## make lookup FREQ=162.55
lookup:
	@$(PYTHON) tools/lookup.py $(FREQ)

clean:
	rm -rf $(BUILD) .build
