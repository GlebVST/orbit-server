import logging
import csv
from io import StringIO
from dateutil.parser import parse as dparse
from django.db import transaction
from django.db.models import Subquery
from users.models import *
from goals.models import GoalType, UserGoal
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
    LICENSE_EXISTS = 'license_exists'
    CREATE_NEW_LICENSE = 'create_new_license'
    CREATE_NEW_LICENSE_NO_UG = 'create_new_license_no_updatable_usergoal'
    UPDATE_LICENSE = 'update_license'
    EDIT_LICENSE_NUMBER= 'edit_license_number'
    LICENSE_INTEGRITY_ERROR = 'license_integrity_error'
    FIELD_NAMES_MAP = {}
    FIELD_NAMES_MAP[OrgFile.DEA] = DEA_LICENSE_FIELD_NAMES
    FIELD_NAMES_MAP[OrgFile.STATE_LICENSE] = STATE_LICENSE_FIELD_NAMES

    def __init__(self, org, admin_user, dry_run=False):
        self.org = org
        self.admin_user = admin_user # used for modifiedBy
        self.dry_run = dry_run
        self.fileType = None
        self.licenseGoalType = GoalType.objects.get(name=GoalType.LICENSE)
        self.lt_state = LicenseType.objects.get(name=LicenseType.TYPE_STATE)
        self.lt_dea = LicenseType.objects.get(name=LicenseType.TYPE_DEA)
        self.data = []
        qset = State.objects.all()
        self.stateDict = {m.abbrev:m for m in qset}
        self.profileDict = {} # (NPI, firstName, lastName) => Profile instance
        self.licenseData = {} # userid => {(stateid, ltypeid, expireDate) => ACTION}
        self.preprocessErrors = [] # error msgs from self.preprocessData
        self.fileHasBlankFields = False
        self.userValidationDict = dict(
            unrecognized=set([]),
            inactive=set([]),
            nonmember=set([])
            )

    def determineFileType(self, src_file):
        """Determine the fileType of the given file based on the column headers.
        If it finds a match, it sets self.fileType.
        Args:
            src_file: Django UploadedFile object that contains csv data
        Returns: None - for no match, or str: matched fileType
        """
        cls = self.__class__
        src_file.seek(0) # file is always empty without this line
        f = StringIO(src_file.read().decode('utf-8'))
        line = f.readline().strip()
        L = line.split(',')
        keys = set([key for key in L if key])
        f.close()
        src_file.close()
        #print(keys)
        self.fileType = None
        self.src_file = None
        for fileType in cls.FIELD_NAMES_MAP:
            fieldNames = set(cls.FIELD_NAMES_MAP[fileType])
            if fieldNames == keys:
                self.fileType = fileType
                self.src_file = src_file
                break
        return self.fileType

    def mapRawDataToModelFields(self, raw_data):
        """Iterate through each row in raw_data and create dict w. keys matching model fieldnames.
        Returns: tuple (data: list of dicts, errors: list of error messages)
        """
        cls = self.__class__
        if self.fileType == OrgFile.STATE_LICENSE:
            stateKey = 'State of Issue'
            licenseNumberKey = 'License Number'
            ltype = self.lt_state
        else:
            stateKey = 'State'
            licenseNumberKey = 'DEA Number'
            ltype = self.lt_dea
        #print('LicenseType: {0}'.format(ltype))
        data = []
        errors = []
        self.fileHasBlankFields = False
        for d in raw_data:
            #print(d)
            lastName = d['Last Name'].strip()
            firstName = d['First Name'].strip()
            npiNumber = d['NPI'].strip()
            licenseNumber = d[licenseNumberKey]
            if not lastName or not firstName or not npiNumber or not licenseNumber:
                self.fileHasBlankFields = True
                continue
            if ',' in licenseNumber:
                msg = "License Number cannot contain comma: {0}".format(licenseNumber)
                logger.warning(msg)
                errors.append(msg)
                continue
            if '?' in licenseNumber:
                msg = "License Number cannot contain question mark: {0}".format(licenseNumber)
                logger.warning(msg)
                errors.append(msg)
                continue
            try:
                state = self.stateDict[d[stateKey].strip().upper()]
            except KeyError:
                msg = 'Invalid state: {0}'.format(d[stateKey])
                logger.warning(msg)
                errors.append(msg)
                continue
            try:
                ed = dparse(d['Expiration Date'].strip())
                expireDate = timezone.make_aware(ed)
            except ValueError:
                msg = 'Invalid date: {0}'.format(d['Expiration Date'])
                logger.warning(msg)
                errors.append(msg)
                continue
            # mapped dict
            md = {
                'npiNumber': d['NPI'].strip(),
                'firstName': d['First Name'].strip(),
                'lastName': lastName,
                'state': state, # State instance
                'licenseNumber': licenseNumber.strip(),
                'licenseType': ltype,
                'expireDate': expireDate
            }
            # 2019-07-23: skip Mary Betterman TM license for now (telemedicine)
            if md['npiNumber'] == '1710962386' and md['licenseNumber'].startswith('TM') and state.abbrev == 'TX':
                logger.warning('Skip {npiNumber}|{state}|{licenseNumber} TM license for now'.format(**md))
                continue
            data.append(md)
        return (data, errors)

    def extractData(self):
        """This should be called after determineFileType method is called.
        It calls mapRawDataToModelFields and sets self.data
        Returns: parseErrors - list of error messages encountered during extraction.
        """
        cls = self.__class__
        fieldNames = cls.FIELD_NAMES_MAP[self.fileType]
        self.src_file.open()
        #print('src_file is readable: {0}'.format(self.src_file.readable()))
        f = StringIO(self.src_file.read().decode('utf-8'))
        reader = csv.DictReader(f,
            fieldnames=fieldNames,
            restkey='extra', dialect='excel')
        all_data = [row for row in reader]
        #print(all_data[0])
        raw_data = all_data[1:]
        # map data to model fields
        data, errors = self.mapRawDataToModelFields(raw_data)
        self.data = data
        return errors

    def validateUsers(self):
        """This should be called after extractData sets self.data
        Set self.profileDict, and initialize the userid keys in self.licenseData.
        Set self.userValidationDict to: {
            inactive: set of inactive users in file,
            nonmember: set of non-member users in file,
            unrecognized: set of users for which Profile could not be identified from (NPI, firstName, lastName)
            }
        """
        cls = self.__class__
        self.profileDict = {} # (NPI, firstName, lastName) => Profile instance
        self.licenseData = {}
        unrecognized = set([])
        nonmember = set([])
        inactive =set([])
        orgmembersByUserid = dict()
        qs = self.org.orgmembers.filter(is_admin=False)
        for m in qs:
            orgmembersByUserid[m.user.pk] = m
        for d in self.data:
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
                unrecognized.add(key)
                #print(key)
                continue
            profile = qs[0]; user = profile.user
            # check org membership of user
            if user.pk in orgmembersByUserid:
                orgm = orgmembersByUserid[user.pk]
                if orgm.removeDate:
                    # user was already removed
                    inactive.add(key)
                else:
                    # user is an active provider in this org
                    self.profileDict[key] = profile
                    self.licenseData[user.pk] = {}
            else:
                nonmember.add(key)
        self.userValidationDict = dict(
            unrecognized=unrecognized,
            inactive=inactive,
            nonmember=nonmember)

    def getAllNonMembers(self):
        """Return consolidated list of users from self.userValidationDict
        Returns: list
        """
        data = []
        for t in self.userValidationDict['unrecognized']:
            data.append(t)
        for t in self.userValidationDict['nonmember']:
            data.append(t)
        for t in self.userValidationDict['inactive']:
            data.append(t)
        return data

    def preprocessData(self):
        """This should be called after validateUsers populates self.profileDict.
        It pre-processes self.data to decide the intended action on each license
        Set self.licenseData: userid => {(expireDate, state.abbrev, ltype.name) => ACTION}
        Set self.preprocessErrors if it encounters license IntegrityErrors.
        Returns: dict {num_new: int, num_upd: int, num_no_action: int, num_error}
        """
        cls = self.__class__
        ltype = self.data[0]['licenseType']
        # query StateLicenses for users in org
        profiles = Profile.objects.filter(organization=self.org)
        sls = StateLicense.objects \
            .filter(
                    licenseType=ltype,
                    is_active=True,
                    user__in=Subquery(profiles.values('pk'))) \
            .select_related('licenseType','state') \
            .order_by('user','licenseType','state','licenseNumber', '-expireDate','-created')
        slDict = {} # userid => (ltypeid, stateid, licenseNumber) => [licenses]
        for sl in sls:
            user = sl.user
            if user.pk not in slDict:
                slDict[user.pk] = {}
            userDict = slDict[user.pk]
            key = (sl.licenseType.pk, sl.state.pk, sl.licenseNumber)
            if key not in userDict:
                userDict[key] = [sl]
            else:
                userDict[key].append(sl)
        # check file rows against slDict & decide action on each row
        num_new = 0; num_upd = 0; num_no_action = 0; num_error = 0
        errors = []
        for d in self.data:
            pkey = (d['npiNumber'], d['firstName'], d['lastName'])
            if pkey not in self.profileDict:
                continue
            profile = self.profileDict[pkey] # Profile instance
            user = profile.user
            lkey = (d['expireDate'], d['state'].abbrev, ltype.name)
            licenseActions = self.licenseData[user.pk] # dict to store intended action on lkey
            userDict = slDict.get(user.pk, {}) # user data from db
            origkey = (ltype.pk, d['state'].pk, d['licenseNumber'])
            key = None
            is_match = False
            if origkey in userDict:
                key = origkey
            else:
                # pad licenseNumber with 0's and check if match
                for idx in range(1,7):
                    lz = '0'*idx + d['licenseNumber'] # left-pad
                    zkey = (ltype.pk, d['state'].pk, lz)
                    if zkey in userDict:
                        logmsg = "Left zero-padded licenseNumber: {0} for: {1}|{2}".format(lz, user, origkey)
                        logger.warning(logmsg)
                        key = zkey
                        break
                    if not key:
                        rz = d['licenseNumber'] + '0'*idx # right-pad
                        zkey = (ltype.pk, d['state'].pk, rz)
                        if zkey in userDict:
                            logmsg = "Right zero-padded licenseNumber: {0} for: {1}|{2}".format(lz, user, origkey)
                            logger.warning(logmsg)
                            key = zkey
                            break
            if key:
                for sl in userDict[key]:
                    if sl.isDateMatch(d['expireDate']):
                        # expireDate matches
                        licenseActions[lkey] = (cls.LICENSE_EXISTS, sl)
                        num_no_action += 1
                        is_match = True
                        break
            if is_match:
                continue
            # key not in userDict: check uniq constraint on SL
            ed = d['expireDate'].replace(hour=12)
            slqs = user.statelicenses.filter(state=d['state'], licenseType=ltype, is_active=True, expireDate=ed)
            if not slqs.exists():
                # brand-new license
                licenseActions[lkey] = (cls.CREATE_NEW_LICENSE, None)
                num_new += 1
            else:
                existing_sl = slqs[0]
                # this license would raise integrity error on StateLicense model
                licenseActions[lkey] = (cls.LICENSE_INTEGRITY_ERROR, None)
                num_error += 1
                logmsg = "IntegrityError for existing_sl: {0.pk}. lkey:{1} and licenseNumber:{2}.".format(existing_sl, lkey, d['licenseNumber'])
                logger.warning(logmsg)
                # msg for end user
                msg = "A {0.state.abbrev} {0.licenseType.name} license for {0.user} exists with a different licenseNumber: {0.licenseNumber}. Please re-verify the licenseNumber for this license.".format(existing_sl)
                errors.append(msg)
            continue
            # expireDate from file does not match any sl in db for the same (ltype, state, licenseNumber).
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
        self.preprocessErrors = errors
        return dict(num_new=num_new, num_upd=num_upd, num_no_action=num_no_action, num_error=num_error)

    def hasWarnings(self):
        """Returns True if file has warnings from:
            fileHasBlankFields: these rows will be ignored if file is processed.
            preprocessErrors exists : these license rows in the file will be ignored if the file is processed
            userValidationDict has inactive/nonmember/unrecognized entries : these users' licenses will be ignored.
        """
        if self.fileHasBlankFields:
            return True
        if self.preprocessErrors:
            return True
        if self.userValidationDict['unrecognized']:
            return True
        if self.userValidationDict['nonmember']:
            return True
        if self.userValidationDict['inactive']:
            return True
        return False

    def processData(self):
        """This should be called after preprocessData. It handles the actions in self.licenseData and updates the db.
        If self.dry_run is set, it returns immediately.
        If exception encountered in creating new license: append key of self.licenseData to self.create_errors.
        If exception encountered in updating license: append key of self.licenseData to self.update_errors.
        Returns: tuple (
            num_action:int - number of license created or updated,
            num_error: int - number of exceptions encountered)
        """
        if self.dry_run:
            return 0
        update_errors = []
        create_errors = []
        num_action = 0
        cls = self.__class__
        ltype = self.data[0]['licenseType']
        for d in self.data:
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
            if action == cls.LICENSE_INTEGRITY_ERROR:
                continue
            #print("{0} for {1}".format(action, lkey))
            if action == cls.EDIT_LICENSE_NUMBER:
                msg = 'Edit License Number of {0.pk}'.format(sl)
                logger.info(msg)
                sl.licenseNumber = d['licenseNumber']
                sl.modifiedBy = self.admin_user
                sl.save()
                num_action += 1
                continue
            if action == cls.UPDATE_LICENSE:
                msg = 'Update existing active License for user {0.user}: {0} to expireDate:{1:%Y-%m-%d}'.format(sl, d['expireDate'])
                #print(msg)
                upd_form_data = {
                    'id': sl.pk,
                    'licenseNumber': d['licenseNumber'],
                    'expireDate': d['expireDate'],
                    'modifiedBy': self.admin_user.pk
                }
                try:
                    serializer = UserLicenseGoalUpdateSerializer(
                            instance=sl,
                            data=upd_form_data
                        )
                    with transaction.atomic():
                        # execute UserLicenseGoalUpdateSerializer
                        serializer.is_valid(raise_exception=True)
                        usergoal = serializer.save() # renew or edit
                        logger.info(msg)
                except Exception as e:
                    logger.exception('Update active license exception')
                    update_errors.append(d)
                    continue
                else:
                    num_action += 1
                    continue
            if action not in (cls.CREATE_NEW_LICENSE, cls.CREATE_NEW_LICENSE_NO_UG):
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
            try:
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
            except Exception as e:
                logger.exception('Create new license exception')
                create_errors.append(d)
                continue
            else:
                num_action += 1
                continue
        self.create_errors = create_errors
        self.update_errors = update_errors
        num_errors = len(create_errors) + len(update_errors)
        return (num_action, num_errors)
