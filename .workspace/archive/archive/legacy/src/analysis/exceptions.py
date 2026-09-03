class AnalysisError(Exception):
    """Base exception for the analysis framework."""
    pass

class PluginRegistrationError(AnalysisError):
    """Raised when there is an error registering or unregistering a plugin."""
    pass

class AnalysisExecutionError(AnalysisError):
    """Raised when an analyzer fails during execution."""
    pass
