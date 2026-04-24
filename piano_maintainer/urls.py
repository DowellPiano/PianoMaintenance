from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from maintenance.views import maintenance_request_form

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('maintenance.urls')),
    path('maintenance_request/<uuid:token>/', maintenance_request_form,
         name='maintenance-request-form'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
