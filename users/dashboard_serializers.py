import logging
from rest_framework import serializers
from .models import AuditReport, Certificate, LicenseType, StateLicense
from .serializers import NestedStateLicenseSerializer

logger = logging.getLogger('gen.dsrl')

class CertificateReadSerializer(serializers.ModelSerializer):
    url = serializers.FileField(source='document', max_length=None, allow_empty_file=False, use_url=True)
    tag = serializers.PrimaryKeyRelatedField(read_only=True)
    state_license = serializers.PrimaryKeyRelatedField(read_only=True)
    class Meta:
        model = Certificate
        fields = (
            'referenceId',
            'url',
            'name',
            'startDate',
            'endDate',
            'credits',
            'tag',
            'state_license',
            'created'
        )
        read_only_fields = fields



class AuditReportReadSerializer(serializers.ModelSerializer):
    npiNumber = serializers.ReadOnlyField(source='user.profile.npiNumber')
    nbcrnaId = serializers.ReadOnlyField(source='user.profile.nbcrnaId')
    degree = serializers.SerializerMethodField()
    statelicense = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    isSampleName = serializers.SerializerMethodField()

    def get_degree(self, obj):
        return obj.user.profile.formatDegrees()

    def get_isSampleName(self, obj):
        """Return True if obj.name starts with Sample Only, else False"""
        return obj.name.startswith('Sample Only')

    def get_statelicense(self, obj):
        """2017-12-20: Add isNurse if condition since we currently
        only support Nurse statelicenses in AuditReport.
        TODO: If need to support multiple licenses, then add:
            state FK and licenseType FK to AuditReport model so that
            serializer knows *which* statelicense to fetch.
        """
        user = obj.user
        if user.profile.isNurse():
            m = StateLicense.objects.getLatestLicenseForUser(user, LicenseType.TYPE_RN)
            if m:
                s =  NestedStateLicenseSerializer(m)
            return s.data
        return None

    def get_country(self, obj):
        """After upgrade to DRF 3.7, use SerializerMethodField because profile.country can be null
        """
        p = obj.user.profile
        if p.country:
            return p.country.code
        return None

    class Meta:
        model = AuditReport
        fields = (
            'referenceId',
            'name',
            'npiNumber',
            'nbcrnaId',
            'country',
            'degree',
            'statelicense',
            'startDate',
            'endDate',
            'saCredits',
            'otherCredits',
            'data',
            'created',
            'isSampleName'
        )
        read_only_fields = fields

