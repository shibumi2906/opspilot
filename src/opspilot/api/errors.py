from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from opspilot.agent.service import RunConflict
from opspilot.auth.context import AuthError
from opspilot.auth.http import denial
from opspilot.config import Settings
from opspilot.runtime.actions import Conflict
from opspilot.security.audit import record
from opspilot.security.freshness import PreconditionsChanged
from opspilot.security.http import response_headers


def install_errors(app: FastAPI, settings: Settings) -> None:
    def error(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            headers=response_headers(settings),
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": False,
                    "request_id": str(uuid4()),
                    "schema_version": 1,
                }
            },
        )

    async def conflict(request: Request, exc: Exception) -> JSONResponse:
        return error("STATE_CONFLICT", "State conflict; refresh the saved result", 409)

    async def missing(request: Request, exc: Exception) -> JSONResponse:
        return error("NOT_FOUND", "Run or action not found", 404)

    async def invalid(request: Request, exc: Exception) -> JSONResponse:
        await record(request.scope, "validation_denied", "VALIDATION_ERROR")
        return error("VALIDATION_ERROR", "Invalid request fields", 422)

    async def internal(request: Request, exc: Exception) -> JSONResponse:
        await record(request.scope, "unexpected_error", "INTERNAL_ERROR")
        return error("INTERNAL_ERROR", "Request could not be completed", 500)

    async def access_denied(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AuthError)
        await record(request.scope, "authorization_denied", exc.code)
        return denial(exc)

    async def database_error(request: Request, exc: Exception) -> JSONResponse:
        if (
            isinstance(exc, DBAPIError)
            and getattr(exc.orig, "sqlstate", None) == "P0001"
            and str(exc.orig).splitlines()[0] == "RUN_ADMISSION_LIMIT"
        ):
            await record(request.scope, "run_admission_denied", "RUN_ADMISSION_LIMIT")
            return error("RUN_ADMISSION_LIMIT", "Active run limit reached", 429)
        return await internal(request, exc)

    app.add_exception_handler(DBAPIError, database_error)
    app.add_exception_handler(AuthError, access_denied)
    app.add_exception_handler(Conflict, conflict)
    app.add_exception_handler(PreconditionsChanged, conflict)
    app.add_exception_handler(RunConflict, conflict)
    app.add_exception_handler(LookupError, missing)
    app.add_exception_handler(RequestValidationError, invalid)
    app.add_exception_handler(Exception, internal)
