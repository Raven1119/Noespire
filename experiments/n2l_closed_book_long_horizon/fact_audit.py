"""Compatibility import for archived experiment runners."""
import sys
from research import fact_audit as _core

sys.modules[__name__] = _core
