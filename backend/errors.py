"""검증 실패를 400 으로 바꾸는 예외 핸들러. 스펙 외 필드만 422 로 남긴다."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

EXTRA_FIELD_ERROR = "extra_forbidden"


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    has_extra_field = any(error.get("type") == EXTRA_FIELD_ERROR for error in errors)
    status_code = 422 if has_extra_field else 400
    return JSONResponse(status_code=status_code, content={"detail": jsonable_encoder(errors)})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)
