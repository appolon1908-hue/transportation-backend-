"""Production ASGI entrypoint.

The foundation application remains unchanged for review continuity.  Production
images import this module, which composes the reviewed core API with the durable
integration endpoints.  Live outbound effects still require an enabled connection,
an enabled subscription, and an explicitly enabled tenant capability.
"""

from app.main import app as app
from app.integrations.api import router as integration_router

if not any(route.path == "/api/v1/admin/integrations/health" for route in app.routes):
    app.include_router(integration_router)

app.title = "Freight Platform API"
app.version = "0.3.0"
