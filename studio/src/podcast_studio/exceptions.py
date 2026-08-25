class PodcastStudioError(Exception):
    """Base exception for user-actionable failures."""


class ValidationError(PodcastStudioError):
    """An artifact or argument failed validation."""


class DependencyError(PodcastStudioError):
    """A required local dependency is unavailable."""


class CommandError(PodcastStudioError):
    """An external command failed."""

    def __init__(self, message: str, *, command: list[str] | None = None, stderr: str = ""):
        super().__init__(message)
        self.command = command or []
        self.stderr = stderr
