"""Constants used by the apps in the Orbit project"""
MAX_URL_LENGTH = 500

# Note: all groups must be created in the database using the Django Group model.
GROUP_CONTENTADMIN = 'ContentAdmin' # Whitelist Admin (and other admin-level site content)
GROUP_CMEREQADMIN = 'CmeReqAdmin'   # to edit Cme Requirements per Specialty (no model yet)
GROUP_ENTERPRISE_ADMIN = 'EnterpriseAdmin'
GROUP_ENTERPRISE_MEMBER = 'EnterpriseMember'

# codenames for permissions
PERM_VIEW_OFFER = u'view_offer'
PERM_VIEW_FEED = u'view_feed'
PERM_POST_SRCME = u'post_srcme'
PERM_POST_BRCME = u'post_brcme'
PERM_DELETE_BRCME = u'delete_brcme'
PERM_EDIT_BRCME = u'edit_brcme'
PERM_VIEW_DASH = u'view_dashboard'
PERM_PRINT_BRCME_CERT = u'print_brcme_cert'
PERM_PRINT_AUDIT_REPORT = u'print_audit_report'
PERM_VIEW_GOAL = u'view_goal'
# default add permission on EligibleSite model
PERM_POST_WHITELIST = u'add_eligiblesite'
# default add permission on RequestedUrl model
PERM_POST_REQUESTED_URL = u'add_requestedurl'
# default add permission on OrgMember model
PERM_MANAGE_ORGMEMBER = u'add_orgmember'
# default add permission on InvitationDiscount model
PERM_ALLOW_INVITE = u'add_invitationdiscount'
ALL_PERMS = (
    PERM_VIEW_OFFER,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_POST_SRCME,
    PERM_POST_BRCME,
    PERM_DELETE_BRCME,
    PERM_EDIT_BRCME,
    PERM_PRINT_AUDIT_REPORT,
    PERM_PRINT_BRCME_CERT,
    PERM_POST_WHITELIST,
    PERM_POST_REQUESTED_URL,
    PERM_VIEW_GOAL,
    PERM_MANAGE_ORGMEMBER,
    PERM_ALLOW_INVITE,
)

SELF_REPORTED_AUTHORITY = u'Self Reported'
# AMA Physician's Recognition Award (PRA) has 2 categories
# Category 1: traditional/formal type of learning activity in mind.
#   These requirements stipulate that the educational content of the activity must
#   be specifically defined; this includes identification of the curriculum and the
#   development of measurable educational objectives.
# Category 2: activities that are self-designated/self-assessed. They do not need to be documented or verified by an external party.
AMA_PRA_CATEGORY_LABEL = u'AMA PRA Category '

#
# Messages for reaching month/year CME limit
#
YEAR_CME_LIMIT_MESSAGE = u'Congratulations! You have earned your credit limit for the year.'

MONTH_CME_LIMIT_MESSAGE = u'You have reached your credit limit for the month. Upgrade your plan to earn credits at unlimited rate.'
