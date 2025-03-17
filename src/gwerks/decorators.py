import os
import warnings
import functools
import sys
import traceback

from gwerks.util import Colors


def deprecated(func):
    """This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""
    @functools.wraps(func)
    def new_func(*args, **kwargs):
        warnings.simplefilter('always', DeprecationWarning)  # turn off filter
        warnings.warn("Call to deprecated function {}.".format(func.__name__),
                      category=DeprecationWarning,
                      stacklevel=2)
        warnings.simplefilter('default', DeprecationWarning)  # reset filter
        return func(*args, **kwargs)
    return new_func


def emitter(override_module_name=None, override_func_name=None):
    def emitter_decorator(func):
        @functools.wraps(func)
        def emitter_wrapper(*args, **kwargs):
            if override_func_name:
                func_name = override_func_name
            else:
                func_name = func.__qualname__

            if override_module_name:
                mod_name = override_module_name
            else:
                mod_name = func.__module__

            with EmitterContext(mod_name, func_name):
                result = func(*args, **kwargs)
                return result
                # try:
                #     result = func(*args, **kwargs)
                #     return result
                # except Exception as e:
                #     raise Exception(f"ERROR in emitter: {e}").with_traceback(None) from None

        return emitter_wrapper
    return emitter_decorator


class EmitterContext:
    def __init__(self, mod_name: str, func_name: str):
        self._stdout = sys.stdout
        self._stderr = sys.stderr

        self._func_name = func_name

        self._mod_name = mod_name.strip()
        if self._mod_name.endswith(":"):
            self._mod_name = self._mod_name[:-1]

    def __enter__(self):
        sys.stdout = self
        sys.stderr = self

    def write(self, msg):
        try:
            msg = msg.strip()
            if len(msg) > 0:
                msg = self._format(msg)
                self._stdout.write(f"{msg}{os.linesep}")
        except Exception as e:
            msg = self._format(f"ERROR: {e}")
            self._stderr.write(f"{msg}{os.linesep}")

    def _format(self, msg):
        # prefix = f"{self._mod_name}.{self._func_name}: "
        prefix = f"{self._func_name}: "
        if msg.startswith("WARN: "):
            msg = f"{Colors.ylw}{prefix}{msg[6:]}{Colors.end}"
        elif msg.startswith("ERROR: "):
            msg = f"{Colors.red}{prefix}{msg[7:]}{Colors.end}"
        elif msg.startswith("SUCCESS: "):
            msg = f"{Colors.grn}{prefix}{msg[9:]}{Colors.end}"
        else:
            msg = f"{Colors.grn}{prefix}{Colors.end}{msg}"
        return f"{msg}"

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            self.write(traceback.format_exc())
        sys.stdout = self._stdout
        sys.stderr = self._stderr

    def flush(self):
        self._stdout.flush()
