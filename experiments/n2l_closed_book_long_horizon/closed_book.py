"""Compatibility import for archived experiment runners."""
import sys
from research import closed_book as _core

sys.modules[__name__] = _core
