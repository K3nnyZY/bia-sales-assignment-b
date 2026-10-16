"""Bound multipart bodies before Starlette spools them to disk, including chunked requests."""

from fastapi import HTTPException
from starlette.responses import JSONResponse

LIMIT = 2 * 1024 * 1024 + 16 * 1024


class KnowledgeUploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not (
                scope["path"].startswith("/api/v1/knowledge/documents/")
                and scope["path"].endswith("/versions")
            )
        ):
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = LIMIT + 1
        if declared > LIMIT:
            return await JSONResponse(
                {"detail": {"code": "FILE_SIZE", "message": "Upload exceeds 2 MiB"}},
                status_code=413,
            )(scope, receive, send)
        count = 0

        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > LIMIT:
                raise HTTPException(
                    413, detail={"code": "FILE_SIZE", "message": "Upload exceeds 2 MiB"}
                )
            return message

        await self.app(scope, bounded_receive, send)
