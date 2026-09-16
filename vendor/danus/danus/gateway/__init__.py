"""DANUS gateway. MCP is optional for in-process submission users."""
from .roles import ALL_TOOLS, ROLE_TOOLS, tools_for


def build_app(*args, **kwargs):
    from .server import build_app as build
    return build(*args, **kwargs)
