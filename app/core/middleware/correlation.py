"""
Correlation ID and Request Scope Context Middleware.

Intercepts incoming HTTP requests to:
1. Extract or generate a unique Correlation ID (`X-Request-ID`).
2. Bind `request_id`, `client_ip`, and `user_agent` to `contextvars` so all log
   records emitted during the request life cycle include these metadata.
3. Attach `X-Request-ID` header to outgoing HTTP responses for client-side tracing.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import client_ip_ctx, request_id_ctx, user_agent_ctx


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique Request/Correlation ID to each HTTP request.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 1. Extract or generate Request ID
        request_id = request.headers.get(self.HEADER_NAME)
        if not request_id or not request_id.strip():
            request_id = str(uuid.uuid4())

        # 2. Extract Client IP & User-Agent
        client_ip = request.client.host if request.client else "unknown"
        # Respect X-Forwarded-For if running behind reverse proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        user_agent = request.headers.get("User-Agent", "unknown")

        # 3. Set ContextVars for logging
        token_req = request_id_ctx.set(request_id)
        token_ip = client_ip_ctx.set(client_ip)
        token_ua = user_agent_ctx.set(user_agent)

        try:
            response = await call_next(request)
            response.headers[self.HEADER_NAME] = request_id
            return response
        finally:
            # Reset ContextVars
            request_id_ctx.reset(token_req)
            client_ip_ctx.reset(token_ip)
            user_agent_ctx.reset(token_ua)
