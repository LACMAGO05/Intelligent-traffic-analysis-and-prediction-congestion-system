
# ROLE BASED ACCESS CONTROL (RBAC)
# Using Django's built-in Groups system
 
# THREE ROLES:
#   Admin     → full access (predict, analytics, retrain, user management)
#   Analyst   → analytics + prediction only (no user management)
#   Commuter  → prediction only

# HOW IT WORKS:
#   1. Create groups in the database (run setup_groups.py once)
#   2. Assign users to groups (in Django admin or signup flow)
#   3. Protect views with @role_required decorator


from django.contrib.auth.models import Group, Permission
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from functools import wraps
 
  
def create_groups():
    """
    Creates the 3 role groups in the database.
    Run this once after setting up your project.
    """
    admin_group,    _ = Group.objects.get_or_create(name='Admin')
    analyst_group,  _ = Group.objects.get_or_create(name='Analyst')
    commuter_group, _ = Group.objects.get_or_create(name='Commuter')
 
    print("✅ Groups created: Admin, Analyst, Commuter")
    return admin_group, analyst_group, commuter_group


# ── Step 2: Decorator to protect views by role ───────────────────────
 
def role_required(*roles):
    """
    Decorator that restricts a view to users with specific roles (groups).
 
    Usage:
        @role_required('Admin', 'Analyst')
        def analytics_view(request): ...
 
        @role_required('Admin')
        def retrain_view(request): ...
 
        @role_required('Admin', 'Analyst', 'Commuter')
        def predict_view(request): ...   # all logged-in users
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            # Superusers bypass all role checks
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
 
            # Check if the user belongs to any of the required groups
            user_groups = request.user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in roles):
                return view_func(request, *args, **kwargs)
 
            # User does not have the required role
            # For API views return JSON, for page views redirect
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse(
                    {"error": "You do not have permission to do this."},
                    status=403
                )
            return redirect('dashboard')  # or render a 403 page
 
        return wrapper
    return decorator
 
 
def get_user_role(user):
    """
    Returns the primary role of a user as a string.
    Used in templates to show/hide navigation items.
    """
    if user.is_superuser:
        return 'Admin'
    groups = list(user.groups.values_list('name', flat=True))
    if 'Admin' in groups:
        return 'Admin'
    if 'Analyst' in groups:
        return 'Analyst'
    if 'Commuter' in groups:
        return 'Commuter'
    return 'Commuter'  # default role for new users
 

# ── Step 3: Context processor — makes role available in ALL templates ─
def role_context(request):
    """
    Makes {{ user_role }} available in every template automatically.
    """
    if request.user.is_authenticated:
        return {"user_role": get_user_role(request.user)}
    return {"user_role": None}