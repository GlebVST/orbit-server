"""Constants used by the apps in the Orbit project"""
from datetime import datetime
import pytz

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

SELF_REPORTED_AUTHORITY = u'Self Reported'
# AMA Physician's Recognition Award (PRA) has 2 categories
# Category 1: traditional/formal type of learning activity in mind.
#   These requirements stipulate that the educational content of the activity must
#   be specifically defined; this includes identification of the curriculum and the
#   development of measurable educational objectives.
# Category 2: activities that are self-designated/self-assessed. They do not need to be documented or verified by an external party.
AMA_PRA_CATEGORY_LABEL = u'AMA PRA Category '

# Sponsor-mandated minium start date allowed for BrowserCme
BRCME_MIN_START_DATE = datetime(2017,8,7,tzinfo=pytz.utc)

PINNED_MESSAGE_TITLE_PREFIX = u'Orbit Stories: '
