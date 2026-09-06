def handle_tool_error(error: Exception) -> str:
    """Return tool failures to the model instead of crashing."""
    return f"Tool call failed: {type(error).__name__}: {error}"
