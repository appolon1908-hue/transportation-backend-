"""Production ASGI entrypoint.

This composes the reviewed core API with durable integrations and the four portal
surfaces. Live outbound effects and external portal access remain capability-gated
and disabled by default.
"""

from app.integrations.api import router as integration_router
from app.integrations.health_api import router as integration_health_router
from app.main import app as app
from app.portals.admin_api import router as portal_admin_router
from app.portals.carrier_api import router as carrier_portal_router
from app.portals.customer_api import router as customer_portal_router
from app.portals.operations_api import router as operations_router
from app.portals.review_api import router as portal_review_router

ROUTERS = (
    (integration_health_router, "/api/v1/admin/integrations/health"),
    (integration_router, "/api/v1/admin/integrations"),
    (portal_admin_router, "/api/v1/admin/portal-bindings"),
    (portal_review_router, "/api/v1/admin/portal-reviews/claims"),
    (operations_router, "/api/v1/operations/control-tower"),
    (customer_portal_router, "/api/v1/portals/customer/context"),
    (carrier_portal_router, "/api/v1/portals/carrier/context"),
)

routers_added = False
for router, sentinel_path in ROUTERS:
    if not any(getattr(route, "path", None) == sentinel_path for route in app.routes):
        app.include_router(router)
        routers_added = True

if routers_added:
    app.openapi_schema = None

app.title = "Freight Platform API"
app.version = "0.6.0"
