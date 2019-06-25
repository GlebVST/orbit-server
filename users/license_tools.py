import logging
import csv
from io import StringIO
from dateutil.parser import parse as dparse
from django.db import transaction
from django.db.models import Subquery
from users.models import *
from goals.models import UserGoal
from goals.serializers import UserLicenseCreateSerializer, UserLicenseGoalUpdateSerializer

logger = logging.getLogger('gen.updsl')

STATE_LICENSE_FIELD_NAMES = (
    'NPI',
    'First Name',
    'Last Name',
    'State of Issue',
    'License Number',
    'Expiration Date'
)
DEA_LICENSE_FIELD_NAMES = (
    'NPI',
    'First Name',
    'Last Name',
    'State',
    'DEA Number',
    'Expiration Date'
)

class LicenseUpdater:
    """Handles updating State or DEA licenses from file"""
    FILE_TYPE_STATE = 'state'
    FILE_TYPE_DEA = 'dea'
    LICENSE_EXISTS = 'license_exists'
    CREATE_NEW_LICENSE = 'create_new_license'
    CREATE_NEW_LICENSE_NO_UG = 'create_new_license_no_updatable_usergoal'
    UPDATE_LICENSE = 'update_license'
    EDIT_LICENSE_NUMBER= 'edit_license_number'
    FIELD_NAMES_MAP = {}
    FIELD_NAMES_MAP[FILE_TYPE_DEA] = DEA_LICENSE_FIELD_NAMES
    FIELD_NAMES_MAP[FILE_TYPE_STATE] = STATE_LICENSE_FIELD_NAMES

    def __init__(self, org, admin_user, dry_run=False):
        self.org = org
        self.admin_user = admin_user # used for modifiedBy
        self.dry_run = dry_run
        self.licenseGoalType = GoalType.objects.get(name=GoalType.LICENSE)
        self.lt_state = LicenseType.objects.get(name=LicenseType.TYPE_STATE)
        self.lt_dea = LicenseType.objects.get(name=LicenseType.TYPE_DEA)
        qset = State.objects.all()
        self.stateDict = {m.abbrev:m for m in qset}
        self.profileDict = {} # (NPI, firstName, lastName) => Profile instance
        self.licenseData = {} # userid => {(stateid, ltypeid, expireDate) => ACTION}

    def validateUsers(self, data):
        """Args:
            data: list of dicts w. keys corresponding to actual model fields
        Sets self.profileDict
        Returns:dict {
            inactive: list of inactive users in file,
            nonmember: list of non-member users in file,
            unrecognized: list of users for which Profile could not be identified from (NPI, firstName, lastName)
            }
        """
        cls = self.__class__
        self.profileDict = {} # (NPI, firstName, lastName) => Profile instance
        unrecognized = []
        nonmember = []
        inactive = []
        orgmembersByUserid = dict()
        qs = self.org.orgmembers.filter(is_admin=False)
        for m in qs:
            orgmembersByUserid[m.user.pk] = m
        for d in data:
            key = (d['npiNumber'], d['firstName'], d['lastName'])
            if key in self.profileDict:
                continue
            fkwargs = {
                'npiNumber': d['npiNumber'],
                'firstName__iexact': d['firstName'],
                'lastName__iexact': d['lastName']
            }
            qs = Profile.objects.filter(**fkwargs)
            if not qs.exists():
                unrecognized.append(key)
                continue
            profile = qs[0]; user = profile.user
            # check org membership of user
            if user.pk in orgmembersByUserid:
                orgm = orgmembersByUserid[user.pk]
                if orgm.removeDate:
                    # user was already removed
                    inactive.append(key)
                else:
                    # user is an active provider in this org
                    self.profileDict[key] = profile
                    self.licenseData[user.pk] = {}
            else:
                nonmember.append(key)
        return dict(
            num_providers=len(self.profileDict),
            unrecognized=unrecognized,
            inactive=inactive,
            nonmember=nonmember)

    def preprocessData(self, ltype, data):
        """Pre-process data to determine the action on each license
        Args:
            ltype: LicenseType instance (either State or DEA)
            data: list of dicts w. keys corresponding to actual model fields
        Sets self.licenseData: userid => {(expireDate, state.abbrev, ltype.name) => ACTION}
        Returns: tuple (num_new, num_upd, num_no_action) for number of intended actions
        """
        cls = self.__class__
        self.licenseData = {} # userid => {(expireDate, state.abbrev, ltype.name) => ACTION}
        # query StateLicenses for users in org
        subqs = Profile.objects.filter(organization=org)
        sls = StateLicense.objects \
            .filter(
                    licenseType=ltype,
                    is_active=True,
                    user__in=Subquery(profiles.values('pk'))) \
            .select_related('licenseType','state') \
            .order_by('user','licenseType','state','-expireDate','-created')
        slDict = {} # userid => (ltypeid, stateid) => [licenses]
        for sl in sls:
            if sl.user.pk not in slDict:
                slDict[user.pk] = {}
            userDict = slDict[user.pk]
            key = (sl.licenseType.pk, sl.state.pk)
            if key not in userDict:
                userDict[key] = [sl]
            else:
                userDict[key].append(sl)
        # check file rows against slDict & decide action on each row
        num_new = 0; num_upd = 0; num_no_action = 0
        for d in data:
            key = (d['npiNumber'], d['firstName'], d['lastName'])
            if key not in self.profileDict:
                continue
            profile = self.profileDict[key] # Profile instance
            user = profile.user
            lkey = (d['expireDate'], d['state'].abbrev, ltype.name)
            licenseActions = self.licenseData[user.pk] # dict to store intended action on lkey
            userDict = slDict[user.pk] # user data from db
            key = (ltype.pk, d['state'].pk)
            if key not in userDict:
                # brand-new license
                licenseActions[lkey] = (cls.CREATE_NEW_LICENSE, None)
                num_new += 1
                continue
            # get latest license for key (latest expireDate)
            sl = userDict[key][0]
            #print('Latest License: {0.pk}|{0.displayLabel)'.format(sl))
            if sl.isDateMatch(d['expireDate']):
                # expireDate matches
                if sl.licenseNumber == d['licenseNumber']:
                    # licenseNumber matches
                    licenseActions[lkey] = (cls.LICENSE_EXISTS, sl)
                    num_no_action += 1
                else:
                    licenseActions[lkey] = (cls.EDIT_LICENSE_NUMBER, sl)
                    num_upd += 1
                continue
            # expireDate from file does not match latest sl in db.
            # is license attached to an updateable license usergoal
            ugs = sl.usergoals.filter(goal__goalType=self.licenseGoalType) \
                    .exclude(status=UserGoal.EXPIRED) \
                    .order_by('-dueDate')
            if not ugs.exists():
                # No updateable usergoal! (corner case)
                licenseActions[lkey] = (cls.CREATE_NEW_LICENSE_NO_UG, sl)
                num_new += 1
            else:
                # renewal or edit-in-place
                licenseActions[lkey] = (cls.UPDATE_LICENSE, sl)
                num_upd += 1
        return (num_new, num_upd, num_no_action)

    def processData(self, ltype, data):
        """This should be called after preprocessData. It handles the actions in self.licenseData and updates the db.
        Args:
            ltype: LicenseType instance (either State or DEA)
            data: list of dicts w. keys corresponding to actual model fields
        If self.dry_run is set, it returns immediately.
        """
        if self.dry_run:
            return False
        cls = self.__class__
        for d in data:
            key = (d['npiNumber'], d['firstName'], d['lastName'])
            if key not in self.profileDict:
                continue
            profile = self.profileDict[key] # Profile instance
            user = profile.user
            licenseActions = self.licenseData[user.pk]
            lkey = (d['expireDate'], d['state'].abbrev, ltype.name)
            action, sl = licenseActions[lkey] # (action, license instance)
            if action == cls.LICENSE_EXISTS:
                continue
            if action == cls.EDIT_LICENSE_NUMBER:
                msg = 'Edit License Number of {0.pk}'.format(sl)
                logger.info(msg)
                sl.licenseNumber = d['licenseNumber']
                sl.modifiedBy = self.admin_user
                sl.save()
                continue
            if action == cls.UPDATE_LICENSE:
                msg = 'Update existing active License: {0.pk}'.format(sl)
                logger.info(msg)
                upd_form_data = {
                    'id': sl.pk,
                    'licenseNumber': d['licenseNumber'],
                    'expireDate': d['expireDate'],
                    'modifiedBy': self.admin_user.pk
                }
                serializer = UserLicenseGoalUpdateSerializer(
                        instance=sl,
                        data=upd_form_data
                    )
                with transaction.atomic():
                    # execute UserLicenseGoalUpdateSerializer
                    serializer.is_valid(raise_exception=True)
                    usergoal = serializer.save() # renew or edit
                continue
            # create new license case
            if action == cls.CREATE_NEW_LICENSE_NO_UG:
                # handle corner case
                sl.inactivate()
            form_data = {
                'user': user.pk,
                'state': d['state'].pk,
                'licenseType': ltype.pk,
                'licenseNumber': d['licenseNumber'],
                'expireDate': d['expireDate'],
                'modifiedBy': self.admin_user.pk
            }
            serializer = UserLicenseCreateSerializer(data=form_data)
            with transaction.atomic():
                # create StateLicense, update profile
                serializer.is_valid(raise_exception=True)
                userLicense = serializer.save()
                msg = "Created new License: {0.pk}".format(userLicense)
                logger.info(msg)
                userLicenseGoals, userCreditGoals = UserGoal.objects.handleNewStateLicenseForUser(userLicense)
                if not userLicenseGoals:
                    raise ValueError('A user licenseGoal for the new license was not found.')
        return True

    def mapRawDataToModelFields(self, fileType, raw_data):
        cls = self.__class__
        if fileType == cls.FILE_TYPE_STATE:
            stateKey = 'State of Issue'
            licenseNumberKey = 'License Number'
            ltype = self.lt_state
        else:
            stateKey = 'State'
            licenseNumberKey = 'DEA Number'
            ltype = self.lt_dea
        data = []
        for d in raw_data:
            #print(d)
            if not d['Last Name']:
                continue
            lastName = d['Last Name'].strip()
            if not lastName:
                continue
            try:
                state = self.stateDict[d[stateKey].strip().upper()]
            except KeyError:
                logger.warning('Invalid state: {0}'.format(d[stateKey]))
                continue
            try:
                expireDate = dparse(d['Expiration Date'].strip())
            except ValueError:
                logger.warning('Invalid date: {0}'.format(d['Expiration Date']))
                continue
            # mapped dict
            md = {
                'npiNumber': d['NPI'].strip(),
                'firstName': d['First Name'].strip(),
                'lastName': lastName,
                'state': state, # State instance
                'licenseNumber': d[licenseNumberKey].strip(),
                'licenseType': ltype,
                'expireDate': expireDate
            }
            data.append(md)
        return data

    def preprocessFile(self, fileType, src_file):
        """Args:
            fileType: str one of FILE_TYPE_DEA, FILE_TYPE_STATE
            src_file: Django UploadedFile object that contains csv data
        Returns: bool - success
        """
        cls = self.__class__
        try:
            fieldNames = cls.FIELD_NAMES_MAP[fileType]
            f = StringIO(src_file.read())
            reader = csv.DictReader(f,
                fieldnames=fieldNames,
                restkey='extra', dialect='excel')
            all_data = [row for row in reader]
            raw_data = all_data[1:]
            f.close()
            # map data to model fields
            data = self.mapRawDataToModelFields(fileType, raw_data)
            ltype = data[0]['licenseType']
            success = self.processData(ltype, data)
        except IOError as e:
            print(str(e))
        else:
            return success
