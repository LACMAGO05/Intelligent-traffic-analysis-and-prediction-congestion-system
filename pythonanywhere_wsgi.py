import os
import sys

# Add your project directory to the sys.path
path = '/home/yourusername/TrafficPro'
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'TrafficPro.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
