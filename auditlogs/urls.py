from rest_framework.routers import DefaultRouter

from .views import AuditLogViewSet

app_name = "auditlogs"

router = DefaultRouter()
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("auditlogs", AuditLogViewSet, basename="auditlog-alias")

urlpatterns = router.urls
