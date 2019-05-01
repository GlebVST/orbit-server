"""AutocompleteFilters used by admin site"""
from dal_admin_filters import AutocompleteFilter

#
# The autocomplete_urls must be created in the respective app's ac_views module
#
class UserFilter(AutocompleteFilter):
    title = 'User'
    field_name = 'user'
    autocomplete_url = 'useremail-autocomplete'

class CmeTagFilter(AutocompleteFilter):
    title = 'CmeTag'
    field_name = 'cmeTag'
    autocomplete_url = 'cmetag-autocomplete'

class StateFilter(AutocompleteFilter):
    title = 'State'
    field_name = 'state'
    autocomplete_url = 'statename-autocomplete'

class HospitalFilter(AutocompleteFilter):
    title = 'Hospital'
    field_name = 'hospital'
    autocomplete_url = 'hospital-autocomplete'

class LicenseGoalFilter(AutocompleteFilter):
    title = 'LicenseGoal'
    field_name = 'licenseGoal'
    autocomplete_url = 'licensegoal-autocomplete'

class AllowedUrlFilter(AutocompleteFilter):
    title = 'AllowedUrl'
    field_name = 'url'
    autocomplete_url = 'aurl-autocomplete'
