#!/usr/bin/env python3
"""Run all Million compiler tests."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess
import sys

tests = [
    ("tests.test_lexer", "Lexer Tests"),
    ("tests.test_parser", "Parser Tests"),
    ("tests.test_end_to_end", "End-to-End Tests"),
]

all_passed = True
for module, name in tests:
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    result = subprocess.run([sys.executable, "-m", module], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        all_passed = False

print(f"\n{'='*50}")
if all_passed:
    print("  ALL TESTS PASSED!")
else:
    print("  SOME TESTS FAILED!")
print(f"{'='*50}")
sys.exit(0 if all_passed else 1)
