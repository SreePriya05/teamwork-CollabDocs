from rest_framework.routers import DefaultRouter

from .views import CommentViewSet, TagViewSet

app_name = "comments"

router = DefaultRouter()
router.register("comments", CommentViewSet, basename="comment")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = router.urls
