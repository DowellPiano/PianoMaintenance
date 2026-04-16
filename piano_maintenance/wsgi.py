"""
WSGI config for piano_maintenance project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "piano_maintenance.settings")

application = get_wsgi_application()
