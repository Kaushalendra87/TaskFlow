import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token):
    """
    Validate a SimpleJWT access token and retrieve its corresponding active user
    using DRF's native authentication pipeline.
    
    database_sync_to_async allows us to perform this database operation 
    safely from async middleware.
    """
    jwt_authentication = JWTAuthentication()

    try:
        validated_token = jwt_authentication.get_validated_token(token)
        user = jwt_authentication.get_user(validated_token)
        
        # Ensure the user exists and is active
        if user is not None and user.is_active:
            return user
            
    except (TokenError, InvalidToken, Exception):
        # Invalid, expired, or otherwise unusable tokens
        pass

    return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Authenticate WebSocket connections using a SimpleJWT access token 
    in the query string.

    Expected query parameter format:
        ws://127.0.0.1:8000/ws/jobs/15/?token=<access_token>
    """

    async def __call__(self, scope, receive, send):
        # Start with a shallow copy of scope to prevent mutation side-effects,
        # defaulting to an unauthenticated AnonymousUser.
        scope = dict(scope)
        scope["user"] = AnonymousUser()

        # Read and decode the query string from the WebSocket URL.
        query_string = scope.get(
            "query_string",
            b"",
        ).decode("utf-8")

        query_params = parse_qs(query_string)

        # Extract the token safely (handles missing keys or empty lists).
        tokens = query_params.get("token", [])
        token = tokens[0] if tokens else None

        if token:
            # Delegate validation and retrieval to our async helper
            scope["user"] = await get_user_from_token(token)
            logger.debug(f"Middleware: user set to {scope['user']}")
        else:
            logger.debug("Middleware: no token, user is AnonymousUser")

        # Pass the updated scope to the next ASGI application.
        return await super().__call__(
            scope,
            receive,
            send,
        )