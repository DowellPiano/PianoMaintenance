from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import LocationViewSet, PianoViewSet

router = DefaultRouter()
router.register(r'locations', LocationViewSet)
router.register(r'pianos', PianoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
