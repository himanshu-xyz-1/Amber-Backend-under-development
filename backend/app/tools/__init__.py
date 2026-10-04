from backend.app.tools.base import tool_registry

# Import to trigger registration
import backend.app.tools.diagnostics  # noqa: F401
import backend.app.tools.remediation  # noqa: F401

__all__ = ["tool_registry"]
