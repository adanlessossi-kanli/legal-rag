"""Structured error codes for machine-readable API error responses."""

from enum import Enum

from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    # Auth
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_ACCOUNT_LOCKED = "AUTH_ACCOUNT_LOCKED"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_TOKEN_REVOKED = "AUTH_TOKEN_REVOKED"
    AUTH_EMAIL_EXISTS = "AUTH_EMAIL_EXISTS"
    AUTH_USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"
    AUTH_INSUFFICIENT_ROLE = "AUTH_INSUFFICIENT_ROLE"

    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_ID_FORMAT = "INVALID_ID_FORMAT"

    # Documents
    DOC_NOT_FOUND = "DOC_NOT_FOUND"
    DOC_ACCESS_DENIED = "DOC_ACCESS_DENIED"
    DOC_DUPLICATE = "DOC_DUPLICATE"
    DOC_UNSUPPORTED_TYPE = "DOC_UNSUPPORTED_TYPE"
    DOC_TOO_LARGE = "DOC_TOO_LARGE"
    DOC_EMPTY = "DOC_EMPTY"

    # Conversations
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"

    # Organizations
    ORG_NOT_FOUND = "ORG_NOT_FOUND"
    ORG_MEMBER_EXISTS = "ORG_MEMBER_EXISTS"
    ORG_ADMIN_REQUIRED = "ORG_ADMIN_REQUIRED"
    ORG_CANNOT_REMOVE_OWNER = "ORG_CANNOT_REMOVE_OWNER"

    # Blueprints
    BLUEPRINT_NOT_FOUND = "BLUEPRINT_NOT_FOUND"
    BLUEPRINT_DEFAULT_PROTECTED = "BLUEPRINT_DEFAULT_PROTECTED"
    BLUEPRINT_ACCESS_DENIED = "BLUEPRINT_ACCESS_DENIED"

    # Chat / RAG
    CHAT_GENERATION_FAILED = "CHAT_GENERATION_FAILED"
    CHAT_TIMEOUT = "CHAT_TIMEOUT"

    # Rate limiting
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Server
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class AppError(HTTPException):
    """Application error with structured error code."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        detail: str,
    ):
        super().__init__(
            status_code=status_code,
            detail={"code": code.value, "message": detail},
        )
        self.code = code
