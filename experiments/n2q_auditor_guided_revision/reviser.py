"""Compatibility import for archived experiment runners."""
import sys
from research.refinement import reviser as _core

sys.modules[__name__] = _core
