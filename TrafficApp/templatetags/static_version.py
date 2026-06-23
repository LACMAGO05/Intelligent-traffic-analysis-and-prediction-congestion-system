"""
Cache-busting static helper.

``{% static_v 'index.js' %}`` behaves like ``{% static %}`` but appends the
file's last-modified time as a ``?v=`` query string, e.g.
``/static/index.js?v=1718900000``. Because the value changes the instant the
file is edited, browsers automatically fetch the new copy — no manual version
bumping. This matters in local development (DEBUG=True), where Django serves
static files as-is without the content-hashed filenames that WhiteNoise's
manifest storage produces in production.
"""
import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    url = static(path)
    source = finders.find(path)  # absolute path of the source file (dev or prod)
    if source and os.path.exists(source):
        version = int(os.path.getmtime(source))
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}v={version}"
    return url
