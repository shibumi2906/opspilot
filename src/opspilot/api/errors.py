from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from opspilot.agent.service import RunConflict
from opspilot.runtime.actions import Conflict


def install_errors(app: FastAPI) -> None:
    def error(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": False,
                    "correlation_id": str(uuid4()),
                }
            },
        )

    async def conflict(request: Request, exc: Exception) -> JSONResponse:
        return error("STATE_CONFLICT", str(exc), 409)

    async def missing(request: Request, exc: Exception) -> JSONResponse:
        return error("NOT_FOUND", "Run or action not found", 404)

    async def invalid(request: Request, exc: Exception) -> JSONResponse:
        return error("VALIDATION_ERROR", "Invalid request fields", 422)

    async def internal(request: Request, exc: Exception) -> JSONResponse:
        return error("INTERNAL_ERROR", "Request could not be completed", 500)

    app.add_exception_handler(Conflict, conflict)
    app.add_exception_handler(RunConflict, conflict)
    app.add_exception_handler(LookupError, missing)
    app.add_exception_handler(RequestValidationError, invalid)
    app.add_exception_handler(Exception, internal)
