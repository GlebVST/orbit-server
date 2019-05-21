import logging
import csv
from cStringIO import StringIO
from dateutil.parser import parse as dparse
from django.db import transaction
from users.models import *
from goals.models import UserGoal
from goals.serializers import UserLicenseCreateSerializer, UserLicenseGoalUpdateSerializer

logger = logging.getLogger('users.updsl')

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
    UPDATE_LICENSE = 'update_license'
    EDIT_LICENSE_NUMBER= 'edit_license_number'
    FIELD_NAMES_MAP = {}
    FIELD_NAMES_MAP[FILE_TYPE_DEA] = DEA_LICENSE_FIELD_NAMES
    FIELD_NAMES_MAP[FILE_TYPE_STATE] = STATE_LICENSE_FIELD_NAMES

    def __init__(self, org, admin_user, dry_run=False):
        self.org = org
        self.admin_user = admin_user # used for modifiedBy
        self.dry_run = dry_run
        self.lt_state = LicenseType.objects.get(name=LicenseType.TYPE_STATE)
        self.lt_dea = LicenseType.objects.get(name=LicenseType.TYPE_DEA)
        qset = State.objects.all()
        self.stateDict = {m.abbrev:m for m in qset}
        self.profileDict = {} # (NPI, firstName, lastName) => Profile instance
        self.licenseData = {} # userid => {(stateid, ltypeid, expireDate) => ACTION}

    def processData(self, ltype, data):
        """Args:
            ltype: LicenseType instance (either State or DEA)
            data: list of dicts w. keys corresponding to actual model fields
            Returns: results
        """
        cls = self.__class__
        self.profileDict = {} # (NPI, firstName, lastName) => Profile instance
        self.licenseData = {} # userid => {(expireDate, state.abbrev, ltype.name) => ACTION}
        for d in data:
            key = (d['npiNumber'], d['firstName'], d['lastName'])
            if key in self.profileDict:
                profile = self.profileDict[key] # Profile instance
            else:
                fkwargs = {
                    'organization': self.org,
                    'npiNumber': d['npiNumber'],
                    'firstName__iexact': d['firstName'],
                    'lastName__iexact': d['lastName']
                }
                qs = Profile.objects.filter(**fkwargs)
                if not qs.exists():
                    print('! No user found: {firstName} {lastName} {NPINumber}'.format(**d))
                    continue
                profile = qs[0]
                self.profileDict[key] = profile
                self.licenseData[profile.pk] = {}
            # check license is either: 1) exists 2) brand-new 3) valid renewal
            user = profile.user
            userLicenseData = self.licenseData[user.pk]
            lkey = (d['expireDate'], d['state'].abbrev, ltype.name)
            qs = StateLicense.objects.filter(
                    user=user,
                    licenseType=ltype,
                    state=d['state'],
                    expireDate__year=d['expireDate'].year,
                    expireDate__month=d['expireDate'].month,
                    expireDate__day=d['expireDate'].day,
                )
            if qs.exists():
                #print('License exists: {0.displayLabel)'.format(sl))
                sl = qs[0]
                if sl.licenseNumber == d['licenseNumber']:
                    userLicenseData[lkey] = cls.LICENSE_EXISTS
                else:
                    msg = 'License Number in file: {licenseNumber} does not match license in db'.format(**d)
                    logger.warning(msg)
                    print(msg)
                    userLicenseData[lkey] = cls.EDIT_LICENSE_NUMBER
                    if not self.dry_run:
                        sl.licenseNumber = d['licenseNumber']
                        sl.modifiedBy = self.admin_user
                        sl.save()
                continue
            # decide if createNew or update
            createNewLicense = False
            fkw = dict(
                is_active=True,
                user=user,
                state=d['state'],
                licenseType=ltype
            )
            #print(fkw)
            qs = StateLicense.objects.filter(**fkw).order_by('-expireDate')
            if not qs.exists():
                # Active (state, licenseType) license does not exist for user
                createNewLicense = True
                msg = '  Active {0.name} {1.abbrev} license not found for {2}'.format(d['state'], ltype, user)
                logger.info(msg)
                print(msg)
            else:
                # Active (state, licenseType) license exists for user
                # Decide if need to renew license or edit in-place
                license = qs[0]
                print('  Found license: {0.displayLabel}'.format(license))
                if license.isUnInitialized():
                    createNewLicense = False
                # is license attached to an updateable usergoal
                ugs = license.usergoals.exclude(status=UserGoal.EXPIRED).order_by('-dueDate')
                if ugs.exists():
                    createNewLicense = False
                else:
                    # No updateable usergoal.
                    createNewLicense = True
                    msg = '   No updateable UserGoal! Create new license'
                    print(msg)
                if createNewLicense:
                    form_data = {
                        'user': user.pk,
                        'state': d['state'].pk,
                        'licenseType': ltype.pk,
                        'licenseNumber': d['licenseNumber'],
                        'expireDate': d['expireDate'],
                        'modifiedBy': self.admin_user.pk
                    }
                    serializer = UserLicenseCreateSerializer(form_data)
                    userLicenseData[lkey] = cls.CREATE_NEW_LICENSE
                else:
                    msg = '  Update existing active License: {0.displayLabel}'.format(license)
                    logger.info(msg)
                    upd_form_data = {
                        'id': license.pk,
                        'licenseNumber': d['licenseNumber'],
                        'expireDate': d['expireDate'],
                        'modifiedBy': self.admin_user.pk
                    }
                    serializer = UserLicenseGoalUpdateSerializer(
                            instance=license,
                            data=upd_form_data
                        )
                    userLicenseData[lkey] = cls.UPDATE_LICENSE
            if self.dry_run:
                continue # skip db transaction
            with transaction.atomic():
                if createNewLicense:
                    # create StateLicense, and update user profile
                    serializer.is_valid(raise_exception=True)
                    userLicense = serializer.save()
                    msg = "Created new License: {0.pk}|{0.displayLabel}".format(userLicense)
                    logger.info(msg)
                    print(msg)
                    userLicenseGoals, userCreditGoals = UserGoal.objects.handleNewStateLicenseForUser(userLicense)
                    if not userLicenseGoals:
                        raise ValueError('A user licenseGoal for the new license was not found.')
                else:
                    # execute UserLicenseGoalUpdateSerializer
                    serializer.is_valid(raise_exception=True)
                    usergoal = serializer.save() # renew or edit
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
            state = self.stateDict[d[stateKey].strip().upper()]
            expireDate = dparse(d['Expiration Date'].strip())
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

    def processFile(self, fileType, src_file):
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
        except IOError, e:
            print(str(e))
        else:
            return success
