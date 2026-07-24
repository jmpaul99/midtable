"""Domain errors raised by services; mapped to HTTP by FastAPI handler."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    def __init__(self, message: Any, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(str(message))


class ConflictError(DomainError):
    def __init__(self, message: Any):
        super().__init__(message, status_code=409)


class ForbiddenError(DomainError):
    def __init__(self, message: Any):
        super().__init__(message, status_code=403)


class NotFoundError(DomainError):
    def __init__(self, message: Any):
        super().__init__(message, status_code=404)
