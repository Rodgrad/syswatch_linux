"""
Minimal entry point for the local pytest shim.

It discovers test modules under `tests`, imports them, and executes any functions
whose names start with ``test_``.  The real pytest framework is not required
for this project's simple tests.
"""
import importlib
import os
import sys
from types import ModuleType

# Discover all files in the 'tests' directory that match *.py and import them.
TEST_DIR = os.path.join(os.path.dirname(__file__), '..', 'tests')
if not os.path.isdir(TEST_DIR):
    sys.exit(0)

failed = 0
for filename in sorted(os.listdir(TEST_DIR)):
    if filename.startswith('_') or not filename.endswith('.py'):
        continue
    module_name = f"tests.{filename[:-3]}"
    try:
        mod: ModuleType = importlib.import_module(module_name)
    except Exception as e:
        print(f"Failed to import {module_name}: {e}")
        failed += 1
        continue
    # Execute any callable starting with 'test_'
    for name in dir(mod):
        if not name.startswith('test_'):
            continue
        func = getattr(mod, name)
        if not callable(func):
            continue
        try:
            func()
        except AssertionError as e:
            print(f"{module_name}.{name} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"{module_name}.{name} ERROR: {e}")
            failed += 1
print('')
if failed:
    sys.exit(1)
else:
    sys.exit(0)
