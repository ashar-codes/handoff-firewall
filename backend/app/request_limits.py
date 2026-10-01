"""Enforce limits on received bytes, including chunked requests with false headers."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .config import settings


class BodyTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, "Request body exceeds limit")


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        count = 0
        exceeded = False
        limit = settings().upload_limit + 1024 * 1024

        async def limited_receive():
            nonlocal count, exceeded
            message = await receive()
            if message["type"] == "http.request":
                count += len(message.get("body", b""))
                if count > limit:
                    exceeded = True
                    raise BodyTooLarge()
            return message

        async def limited_send(message):
            if exceeded:
                # Some request parsers translate receive failures to HTTP 400.
                # Preserve the precise response without buffering the request.
                if message["type"] == "http.response.start":
                    await JSONResponse(
                        status_code=413, content={"detail": "Request body exceeds limit"}
                    )(scope, receive, send)
                return
            await send(message)

        await self.app(scope, limited_receive, limited_send)
