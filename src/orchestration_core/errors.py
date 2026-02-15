class OrchestrationError(Exception):
    """Base exception for orchestration_core."""


class ValidationError(OrchestrationError):
    """State/config is invalid for the requested operation."""


class NotRunningError(OrchestrationError):
    """Requested operation requires a running server, but it isn't running."""

