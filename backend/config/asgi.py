import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings",
)

# Initialize Django before importing modules that
# access Django models or the application registry.
django_asgi_app = get_asgi_application()

from realtime.middleware import JWTAuthMiddleware
from realtime.routing import websocket_urlpatterns


application = ProtocolTypeRouter(
    {
        # Normal HTTP requests continue going to Django.
        "http": django_asgi_app,

        # WebSocket connections go through JWT authentication, 
        # and finally route to consumers.
        "websocket": JWTAuthMiddleware(
            URLRouter(
                websocket_urlpatterns
            )
        ),
    }
)