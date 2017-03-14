"""Constants used by the apps in the Orbit project"""

MAX_URL_LENGTH = 500

# Note: all groups must be created in the database using the Django Group model.
GROUP_CONTENTADMIN = 'ContentAdmin' # Whitelist Admin (and other admin-level site content)
GROUP_CMEREQADMIN = 'CmeReqAdmin'   # to edit Cme Requirements per Specialty (no model yet)

# codenames for permissions
PERM_VIEW_OFFER = u'view_offer'
PERM_VIEW_FEED = u'view_feed'
PERM_POST_SRCME = u'post_srcme'
PERM_POST_BRCME = u'post_brcme'
PERM_VIEW_DASH = u'view_dashboard'
PERM_PRINT_BRCME_CERT = u'print_brcme_cert'
PERM_PRINT_AUDIT_REPORT = u'print_audit_report'
# default add permission on EligibleSite model
PERM_POST_WHITELIST = u'add_eligiblesite'
# default add permission on RequestedUrl model
PERM_POST_REQUESTED_URL = u'add_requestedurl'
ALL_PERMS = (
    PERM_VIEW_OFFER,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_POST_BRCME,
    PERM_POST_SRCME,
    PERM_PRINT_AUDIT_REPORT,
    PERM_PRINT_BRCME_CERT,
    PERM_POST_WHITELIST,
    PERM_POST_REQUESTED_URL
)


