# Nightly synch to an Email Service Provider (ESP) of users and custom fields 

# API utilities: Users.espSync.py
# Management Command: users.management.commands.emailSync.py
# Bash Script: admin_scripts.run_email_sync.sh
from collections import OrderedDict
import hashlib
import inspect
import requests, json

from django.conf import settings

from users.models.base import Profile


class EspApiBackend(object):
    """
    Generic Class for syncing contacts with Email Service Provider (ESP) APIs, such as Mailchimp.
    This assumes a valid account and Access Key.

    for Mailchimp to work, the following variables are required in settings:
    ORBIT_MAILCHIMP_API_KEY
    ORBIT_MAILCHIMP_USERNAME

    the following setting is optional:
    SYNC_EMAIL_SERVICE_PROVIDER
    ...if not supplied, 'Mailchimp' is default.

    If another Email Service Provider is supported, a new derived Class will need to be written
    with the following required variables:
    ESP_NAME, BASE_URL, CLIENTID, SECRET, LOOKUP_FIELD_ESP, SYNC_FIELD_MAP_ESP_TO_LOCAL

    ...and the following required functions:
    espIsReady
    _getEspContactList
    _buildEspContactDicts
    updateEspContacts

    Please see MailchimpApi for an example of a complete derived Class.
    For flow, please see the management command in management.commands.emailSync
    """

    LOOKUP_FIELD_LOCAL = "user_id"

    # Required variables that must be specified by the derived class.
    # See MailchimpApi for example.
    ESP_NAME = ""
    BASE_URL = ""
    CLIENTID = ""
    SECRET = ""
    LOOKUP_FIELD_ESP = "" # Ex: 'email_address', if that's how the ESP identifies contacts
    SYNC_FIELD_MAP_ESP_TO_LOCAL = {} # ESP Fieldnames in ESP's terminology mapped to local fields, in local terminology. See MailchimpApi for example.

    def __init__(self, timeout = 30, headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}):

        self.timeout = timeout
        self.headers = headers

        # During synch, these will be filled with dictionaries of values relevant for users to create, update, and remove, at the ESP level.
        self.toCreate = []
        self.toUpdate = []
        self.toRemove = []

        if self.ESP_NAME == "":
            self._notImplementedError(name="ESP_NAME", hint="This may be 'Mailchimp', 'SendGrid', etc.")  
        if self.BASE_URL == "":
            self._notImplementedError(name="BASE_URL", hint="This should be the name of the field the base url from which API endpoints are built.")       
        if self.CLIENTID  == "":
            self._notImplementedError(name="CLIENTID", hint="This may be your account username.") 
        if self.SECRET == "":
            self._notImplementedError(name="SECRET", hint="This may be an API key.")
        if self.LOOKUP_FIELD_ESP == "":
            self._notImplementedError(name="LOOKUP_FIELD_ESP", hint="This should be the name of the field the Email Service Provider uses to identify contacts, such as 'email'.")      
        if len(self.SYNC_FIELD_MAP_ESP_TO_LOCAL) == 0:
            hint = ("This should be a dictionary mapping field names between Email Service Provider and local data structure."
                    "For example: {'FNAME':'first_name', ...} ")
            self._notImplementedError(name="SYNC_FIELD_MAP_ESP_TO_LOCAL", hint=hint)
        else:
            self.SYNC_FIELD_MAP_LOCAL_TO_ESP = OrderedDict({v: k for k, v in self.SYNC_FIELD_MAP_ESP_TO_LOCAL.items()})

    def _buildErrorMessge(self, status_code, error_text):
        function_name = inspect.currentframe().f_code.co_name
        error_message = "%s %s: bad status code: %s.\nText: %s" % (self.ESP_NAME, function_name, status_code, error_text)
        return error_message

    def _notImplementedError(self, name, hint=None):
        message = "%s does not have %s implemented" % (self.ESP_NAME, name)
        if hint:
            message += "\nHINT: %s" % (hint)
        raise NotImplementedError(message)
 
    def _buildDataDict(self, master_source, lookup_fieldname, sync_map_values, xform_map = None):
        """Takes a master dictionary which may be a flat queryset from local data,
        or may be an assembled dictionary from ESP, if all users and field names/values.
        Returns a dictionary standardized for comparison, with the key as specified by the lookup_fieldname (ex: ids, or email addresses)
        and value another dictionary full of fieldname/field data key/value pairs.
        """
        data_dict = {}
        for udict in master_source:
            lookup_value = str(udict[lookup_fieldname])
            if lookup_value and lookup_value != "":
                profile_data = OrderedDict()
                for attr in sync_map_values:
                    val =  str(udict[attr])
                    # Transform local field name to ESP field name so we always compare using same field name terminology
                    if xform_map:
                        transformed_attr = xform_map.get(attr)
                        profile_data.update({ transformed_attr: val })
                    else:
                        profile_data.update({ attr: val })
                data_dict.update({lookup_value : profile_data})

        return data_dict

    def compareData(self):
        """Compares user profile/subscriber data from local database to ESP data for desired fields.
        Adds dictionaries to self.toCreate, self.toUpdate, and self.toRemove, as appropriate.
        Dictionary has a key of ESP lookup value (for example, an email address) and the value of another dictionary,
        with that dictionary's keys formatted to the field names the ESP expects, but with local data.
        Example:
        self.toCreate = [{'example@example.com': {'fname':'Jane', 'lname':'Doe', 'email':'example@example.com'}}]
        """     
        esp_master_source=self._getEspContactList()
        esp_user_profiles_by_local_lookup = self._buildDataDict(
                master_source=esp_master_source, 
                lookup_fieldname=self.SYNC_FIELD_MAP_LOCAL_TO_ESP.get(self.LOOKUP_FIELD_LOCAL), 
                sync_map_values=self.SYNC_FIELD_MAP_ESP_TO_LOCAL.keys())
        esp_user_profiles_by_esp_lookup = self._buildDataDict(
                master_source=esp_master_source,
                lookup_fieldname=self.LOOKUP_FIELD_ESP, 
                sync_map_values=self.SYNC_FIELD_MAP_ESP_TO_LOCAL.keys())
        local_user_profiles_by_local_lookup = self._buildDataDict(
                master_source=Profile.objects.all().values(),
                lookup_fieldname=self.LOOKUP_FIELD_LOCAL,
                sync_map_values=self.SYNC_FIELD_MAP_ESP_TO_LOCAL.values(), 
                xform_map=self.SYNC_FIELD_MAP_LOCAL_TO_ESP)

        # Create a dictionary linking local id to likely ESP id
        sync_value_map_local_id_to_esp_id_for_users = {}
        for k,v in local_user_profiles_by_local_lookup.items():
            esp_id = v.get(self.LOOKUP_FIELD_ESP)
            sync_value_map_local_id_to_esp_id_for_users.update({k: esp_id})

        for local_id, local_data_dict in local_user_profiles_by_local_lookup.items():
            local_data_tuple = tuple(local_data_dict.values())
            esp_data_dict = esp_user_profiles_by_local_lookup.get(local_id)

            if esp_data_dict:
                # If we can find the user in ESP based on previously synced local identifier
                esp_data_tuple = tuple(esp_data_dict.values())
                if local_data_tuple != esp_data_tuple:
                    # Their data differs. Update it!
                    esp_id = esp_data_dict.get(self.LOOKUP_FIELD_ESP)
                    self.toUpdate.append({esp_id: local_data_dict})
            else:
                # We can't find this user by pk/profile_id.
                esp_id = local_data_dict.get(self.LOOKUP_FIELD_ESP)
                if esp_id:
                    esp_data_dict = esp_user_profiles_by_esp_lookup.get(esp_id)
                    if esp_data_dict:
                        esp_data_tuple = tuple(esp_data_dict.values())
                        if local_data_tuple != esp_data_tuple:
                            esp_id = sync_value_map_local_id_to_esp_id_for_users.get(local_id)
                            self.toUpdate.append({esp_id: local_data_dict})
                    else:
                        # Can't find in esp by local or esp lookups. Must be new.
                        self.toCreate.append({esp_id: local_data_dict})            
                else:
                    # Can't find in esp by local or esp lookups. Must be new.
                    self.toCreate.append({esp_id: local_data_dict}) 

        # Users that exist in mailchimp by local id but don't locally, were presumed deleted locally.
        # Note, to allow for test subscribers,  we don't check for mailchimp contacts that have no local id,
        # and only exist in Mailchimp.
        local_ids = set(local_user_profiles_by_local_lookup.keys())
        esp_profile_ids = set(esp_user_profiles_by_local_lookup.keys())
        differences = list(esp_profile_ids.difference(local_ids))
        for local_id in differences:
            esp_data_dict = esp_user_profiles_by_local_lookup.get(local_id)
            esp_id = esp_data_dict.get(self.LOOKUP_FIELD_ESP)
            self.toRemove.append({esp_id : esp_data_dict})
        # If you delete a contact you can never put that emial address back on the list via the API!
        # But it can be done via GUI.
        return True

    def espIsReady(self):
        """This should be overridden by derived Class,
        to create a function that will check that Email Service Provider is ready for Sync.
        """
        function_name = inspect.currentframe().f_code.co_name
        self._notImplementedError(function_name)

    def _getEspContactList(self):
        """This should be overridden by derived Class,
        It should query ESP API for contacts, and return a list of dictionaries of
        all contacts and relevant fields and data, as identified in SYNC_FIELD_MAP_ESP_TO_LOCAL.
        """
        function_name = inspect.currentframe().f_code.co_name
        self._notImplementedError(function_name)

    def updateEspContacts(self):
        """This should be overridden by derived Class,
        to create a function that will update ESP with selected contacts with selected data.
        Of course exactly how will vary from one Email Service Provider to another.
        """
        function_name = inspect.currentframe().f_code.co_name
        self._notImplementedError(function_name)

class MailchimpApi(EspApiBackend):
    """Mailchimp-specific API interactions"""

    # Required variables, for any derived class inheriting from EspApiBackend:
    ESP_NAME = "Mailchimp"
    LOOKUP_FIELD_ESP = "email_address"
    SYNC_FIELD_MAP_ESP_TO_LOCAL = OrderedDict({'USER_ID': 'user_id', 'email_address': 'contactEmail',
            'FNAME':'firstName', 'LNAME':'lastName'})

    # Mailchimp-specific variables:
    LIST_ID = None
    # CUSTOM_FIELDS are fields we have added, other than Mailchimp's default: ADDRESS, BIRTHDAY, FNAME, LNAME, PHONE
    # They do not have to be all caps when creating, but they do need to be caps when updating, so might as well be consistent.
    # Mailchimp will allow max 10 chars for replacement tags, so if you want them to be consistent, try to keep all field names < 10 chars
    CUSTOM_FIELDS = {'USER_ID': {'type':'text'}}
    # Mailchimp supplies default: ADDRESS, BIRTHDAY, FNAME, LNAME, PHONE. DEFAULT_MERGE_FIELDS specified whcih of those we care to sync.
    DEFAULT_MERGE_FIELDS = ["FNAME", "LNAME"]
    ALL_MERGE_FIELDS = DEFAULT_MERGE_FIELDS + list(CUSTOM_FIELDS.keys())

    def __init__(self):

        try:
            self.SECRET = settings.ORBIT_MAILCHIMP_API_KEY
            self.CLIENTID = settings.ORBIT_MAILCHIMP_USERNAME
        except:
            raise AttributeError("Please provide ORBIT_MAILCHIMP_API_KEY and ORBIT_MAILCHIMP_USERNAME in settings")

        try:
            DATA_CENTER = self.SECRET.split("-")[1]
        except:
            raise ValueError("API Key not in expected format")
        self.BASE_URL = 'https://%s.api.mailchimp.com/3.0/' % (DATA_CENTER)

        self.auth = (self.CLIENTID, self.SECRET)
        super(MailchimpApi, self).__init__()

    def _getListId(self):
        """
        Gets ID of contact list from MailChimp.
        Expects to find a list with the same name as specified in settings.ORBIT_EMAIL_SYNC_LIST_NAME.
        If no list has expected name, will throw exception.
        """
        if self.LIST_ID:
            return self.LIST_ID
        else:
            list_id = None

        url = '%slists' % (self.BASE_URL)
        results = requests.get(url, auth=self.auth, headers=self.headers, timeout=self.timeout)

        if results.status_code != 200:
            error_message = self._buildErrorMessge(results.status_code, results.text)
            raise ValueError(error_message)

        results_json = results.json()

        if len(results_json["lists"]) != 1:
            for l in results_json['lists']:
                i = results_json["lists"].index(l)
                list_name = results_json['lists'][i]["name"]
                if list_name == settings.ORBIT_EMAIL_SYNC_LIST_NAME:
                    list_id = results_json["lists"][i]["id"]
                    break
        else:
            list_name = results_json["lists"][0]["name"]
            if list_name == settings.ORBIT_EMAIL_SYNC_LIST_NAME:
                list_id = results_json["lists"][0]["id"]

        if list_id == None:
            raise ValueError("Error finding Mailchimp subscriber list by name of %s" % (settings.ORBIT_EMAIL_SYNC_LIST_NAME))   
        else:
            self.LIST_ID = list_id

        return self.LIST_ID

    def _getMergeFields(self):
        """Checks which merge fields exist for master list,
        returns list of merge field names
        """
        existing_merge_fields = []

        list_id = self._getListId()
        url = '%slists/%s/merge-fields' % (self.BASE_URL, list_id)
        results = requests.get(url, auth=self.auth, headers=self.headers, timeout=self.timeout)

        if results.status_code != 200:
            error_message = self._buildErrorMessge(results.status_code, results.text)
            raise ValueError(error_message)

        results_json = results.json()
        merge_fields = results_json["merge_fields"]
        for mf in merge_fields:
            i = merge_fields.index(mf)
            field_name = merge_fields[i]["name"]
            existing_merge_fields.append(field_name)

        return existing_merge_fields

    def _syncMergeFields(self):
        """Ensures Mailchimp list has desired merge fields.
        Please note that this does not delete merge fields, only adds them.
        """
        existing_merge_fields = self._getMergeFields()
        update_data = {}
        # Add our local Custom Merge Fields if not found in Mailchimp.
        for field in self.CUSTOM_FIELDS.keys():
            if field not in existing_merge_fields:
                update_data.update({
                    'name': field.upper(),
                    'type': self.CUSTOM_FIELDS[field]['type'],
                    'tag': field.upper(),
                })
        if len(update_data) > 0:
            list_id = self._getListId()
            url = '%slists/%s/merge-fields' % (self.BASE_URL, list_id) 
            results = requests.post(url, auth=self.auth, headers=self.headers, timeout=self.timeout, json=update_data)
            if results.status_code == 200:
                return True
            else:
                return False
        else:
            # Merge fields look as they should; nothing to be done.
            return True

    def espIsReady(self):
        """Checks that Merge Fields are created, and List is identified.
        """
        self._getListId()
        self._getMergeFields()
        self._syncMergeFields()

        return True

    def _getListMembers(self):
        """Gets contact list from Mailchimp, returns API reponse.
        """
        list_id = self._getListId()
        url = '%slists/%s/members' % (self.BASE_URL, list_id)
        results = requests.get(url, auth=self.auth, headers=self.headers, timeout=self.timeout)

        if results.status_code != 200:
            error_message = self._buildErrorMessge(results.status_code, results.text)
            raise ValueError(error_message)

        return results

    def _getEspContactList(self):
        """Queries Mailchimp API for contacts, and return a list of flat dictionaries of
        all contacts and relevant fields and data, as identified by SYNC_FIELD_MAP_ESP_TO_LOCAL.
        """

        contact_list = []
        results = self._getListMembers()
        subscriber_json = results.json()['members']
        for s in subscriber_json:
            subscriber_dict = {}
            i = subscriber_json.index(s)
            for field_name in self.SYNC_FIELD_MAP_ESP_TO_LOCAL.keys():
                if field_name in self.ALL_MERGE_FIELDS:
                    field_data = subscriber_json[i]['merge_fields'][field_name]
                else:
                    field_data = subscriber_json[i][field_name]
                subscriber_dict.update({field_name : field_data})
            contact_list.append(subscriber_dict)

        return contact_list

    def _buildEspContactPayload(self, contact_dict, status='subscribed'):
        """
        Formats and returns the dictionary to be submitted to Mailchimp to create or update subscriber record.
        Receives a flat dict of local data using ESP field names for ESP contact to be updated or created,
        builds and returns a new dict in format that is expected by ESP.
        """

        all_sync_fields = list(self.SYNC_FIELD_MAP_ESP_TO_LOCAL.keys())
        non_merge_fields = list(set(all_sync_fields).difference(set(self.ALL_MERGE_FIELDS)))

        # Either 'status_if_new' or 'status' is required by Mailchimp for new subscriber.
        data = {'status': status}
        for field in non_merge_fields:
            val = contact_dict.get(field)
            data.update({field : val})

        merge_fields = {}
        for field in self.ALL_MERGE_FIELDS:
            val = contact_dict.get(field)
            merge_fields.update({field : val})
        data.update({'merge_fields': merge_fields})      

        return data

    def _addToBatchOperationsList(self, batch_operations_list, email_address, contact_dict, status='subscribed'):
        """Takes information, formats it to dictionary which can be added to batch_operations_list for a batch update.
        """
        list_id = self._getListId()
        email_hash = hashlib.md5(email_address.lower().encode('utf-8')).hexdigest()
        path = '/lists/%s/members/%s/' % (list_id, email_hash)

        data = self._buildEspContactPayload(contact_dict=contact_dict, status=status)
        batch_operations_list.append({"method" : "PUT", "path" : path, "body": json.dumps(data)})
        return batch_operations_list

    def _createBatchOperation(self, batch_operations_list):
        """Creates a batch operation to create or update many users with one API call."""
        url = '%sbatches' % (self.BASE_URL)
        data =  {'operations' : batch_operations_list}
        results = requests.post(url, auth=self.auth, headers=self.headers, timeout=self.timeout, json=data)

        if results.status_code != 200:
            error_message = self._buildErrorMessge(results.status_code, results.text)
            raise ValueError(error_message)

        return results

    def updateEspContacts(self):
        """Uses dictionary lists from self.toCreate, self.toUpdate, and self.toRemove,
        to update contact data in Mailchimp.
        Expects dictionary list to use Mailchimp contact email address as key.
        Note the user email address may have, changed, but the previous email is needed to identify & update contact via Mailchimp.
        Because a deleted contact cannot be re-added via the Mailchimp API (only manually or through email verification),
        stale users will not be deleted, only marked as 'unsubscibed' so that they will no longer receive emails.
        """
        batch_id = None
        # Updating and Creating contact in Mailchimp can be done in the same way.
        batch_operations_list = []
        for l in [self.toUpdate, self.toCreate]:
            for d in l:
                for k,v in d.items():
                    batch_operations_list = self._addToBatchOperationsList(batch_operations_list, k, v)

        # If you delete a contact in Mailchimp, you cannot add that email address again programatically without them confirming via email.
        # Better to keep the contact and mark as 'cleaned' or 'unsubscribed'
        for d in self.toRemove:
            for k,v in d.items():
                batch_operations_list = self._addToBatchOperationsList(batch_operations_list, k, v, status="unsubscribed")
       
        batch_results = self._createBatchOperation(batch_operations_list)
        batch_id = batch_results.json()['id']

        if batch_id:
            return True
