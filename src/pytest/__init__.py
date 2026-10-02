"""
Minimal pytest shim.

Provides a very small subset of the real pytest API sufficient for the test suite in this project.
"""
import sys
from types import ModuleType

class _Mark:
    def parametrize(self, argnames, argvalues):
        """Decorate a test function with parameter values.

        The decorator creates multiple new functions in the same module where the original
        is defined. Each generated function calls the original implementation with the
        supplied arguments. This mimics ``pytest.mark.parametrize`` just enough for our
        simple tests.
        """
        def decorator(func):
            # Resolve argument names to a list
            if isinstance(argnames, str):
                names = [argnames]
            else:
                names = list(argnames)
            module = sys.modules[func.__module__]
            for idx, values in enumerate(argvalues):
                if not isinstance(values, (list, tuple)):
                    values = [values]
                args_dict = dict(zip(names, values))
                # Create a new function that forwards to the original
                def wrapper(*_, **__):  # noqa: E741
                    return func(**args_dict)
                # Give the function a unique name so pytest can discover it
                wrapper.__name__ = f"{func.__name__}_{idx}"
                wrapper.__doc__ = func.__doc__
                setattr(module, wrapper.__name__, wrapper)
            # Return the original to avoid accidental execution
            return func
        return decorator

mark = _Mark()

# Export minimal attributes that tests or other code might expect.
__all__ = ["mark"]
