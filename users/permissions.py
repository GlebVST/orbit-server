from rest_framework import permissions

class IsAdminOrAuthenticated(permissions.BasePermission):
    """Global permission (can be used for both list/detail) to check
    that User must be:
        Authenticated: for SAFE_METHODS
        Admin user: for other methods
    What this does:
        ListCreateView: list allows any authenticated user, but
            create requires that user must be admin.
        RetrieveUpdateDestroyView: retrieve allows any authenticated
            user, but update/destroy requires admin user.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff


class IsOwnerOrAuthenticated(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has a `user` attribute.
    User must be:
        Authenticated: for SAFE_METHODS
        Owner: for other methods
    """
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user.pk == request.user.pk


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has a `user` attribute.
    User must be:
        Admin: for SAFE_METHODS
        Owner: for other methods
    """
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        is_owner = obj.user.pk == request.user.pk
        if request.method in permissions.SAFE_METHODS:
            return is_owner or request.user.is_staff
        return is_owner


class IsEntryOwner(permissions.BasePermission):
    """
    Object-level permission used by Update views for Entry children
    Assumes the model instance has a `entry.user` attribute.
    """
    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        is_owner = obj.entry.user.pk == request.user.pk
        return is_owner

