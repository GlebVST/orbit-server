from rest_framework import permissions
from django.contrib.auth.models import Group, Permission
from common.appconstants import (
    GROUP_CONTENTADMIN,
    GROUP_CMEREQADMIN,
    GROUP_ENTERPRISE_ADMIN,
    GROUP_ENTERPRISE_MEMBER,
    PERM_VIEW_OFFER,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_POST_BRCME,
    PERM_DELETE_BRCME,
    PERM_POST_SRCME,
    PERM_PRINT_AUDIT_REPORT,
    PERM_PRINT_BRCME_CERT
)
from .models import ENTRYTYPE_BRCME, UserSubscription

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

class IsContentAdminOrAny(permissions.BasePermission):
    """Global permission (can be used for both list/detail) to check
    that User must be:
        AllowAny: for SAFE_METHODS
        user belongs ContentAdmin group: for other methods
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        elif not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return request.user.groups.filter(name=GROUP_CONTENTADMIN).exists()


class IsEnterpriseAdmin(permissions.BasePermission):
    """Global permission to check that User belongs to EnterpriseAdmin group (for all methods, safe or otherwise).
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return request.user.groups.filter(name=GROUP_ENTERPRISE_ADMIN).exists()


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


def hasUserSubscriptionPerm(user, codename):
    """Gets the latest UserSubscription for the user
    and checks if the permission given by codename
    has the group of the subscription's display_status.
    This expects a Group exists in the database for each
    UserSubscription.display_status and assigned the
    intended permissions.
    Returns: bool
    """
    user_subs = UserSubscription.objects.getLatestSubscription(user)
    if not user_subs:
        return False
    #p = Permission.objects.get(codename=codename)
    p = Permission.objects.filter(codename=codename).order_by('id')[0]
    return p.group_set.filter(name=user_subs.display_status)

class CanViewOffer(permissions.BasePermission):
    """Global permission (can be used for both list/detail) to check
        that user has the permission: PERM_VIEW_OFFER via the
        latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_VIEW_OFFER)

class CanViewFeed(permissions.BasePermission):
    """Global permission (can be used for both list/detail) to check
        that user has the permission: PERM_VIEW_FEED via the
        latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_VIEW_FEED)

class CanViewDashboard(permissions.BasePermission):
    """Global permission to check that user has the permission:
        PERM_VIEW_DASH via the latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_VIEW_DASH)

class CanPrintCert(permissions.BasePermission):
    """Global permission to check that user has the permission:
        PERM_PRINT_BRCME_CERT via the latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_PRINT_BRCME_CERT)

class CanPrintAuditReport(permissions.BasePermission):
    """Global permission to check that user has the permission:
        PERM_PRINT_AUDIT_REPORT via the latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_PRINT_AUDIT_REPORT)

class CanPostSRCme(permissions.BasePermission):
    """Global permission to check that user has the permission:
        PERM_POST_SRCME via the latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_POST_SRCME)

class CanPostBRCme(permissions.BasePermission):
    """Global permission to check that user has the permission:
        PERM_POST_BRCME via the latest subscription.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_active and request.user.is_authenticated()):
            return False
        return hasUserSubscriptionPerm(request.user, codename=PERM_POST_BRCME)


class CanInvalidateEntry(permissions.BasePermission):
    """Object-level permission used by InvalidateEntry view
    For br-cme: only allow it for users with UnlimitedCme plans
    """
    def has_object_permission(self, request, view, obj):
        if obj.entryType.name == ENTRYTYPE_BRCME:
            # get user's plan
            user_subs = UserSubscription.objects.getLatestSubscription(request.user)
            if not user_subs:
                return False
            return user_subs.plan.isUnlimitedCme()
        else:
            return True
