import logging

from django.db import models
from django.db import transaction
from users.models import SubSpecialty, Profile, ResidencyProgram
import re

logger = logging.getLogger('gen.models')

class ResidencyProgramType(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text='Training program type. Must be unique.')
    duration_years = models.IntegerField(default=0, help_text="Program duration in years.")
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Residency(models.Model):
    residency = models.ForeignKey(ResidencyProgram, null=False, on_delete=models.PROTECT, help_text='Residency/facility reference.')
    program_type = models.ForeignKey(ResidencyProgramType, null=False, on_delete=models.PROTECT, help_text='Training program type.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

class OrbitProcedure(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text='Orbit Procedure name. Must be unique.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class OrbitProcedureMatch(models.Model):
    facility = models.CharField(max_length=200, null=False, help_text='Facility name (i.e. UCSD).')
    procedure = models.ForeignKey(OrbitProcedure, null=False, on_delete=models.CASCADE, help_text='Procedure reference for this match.')
    regex = models.CharField(max_length=500, null=False, help_text='Procedure name regex for this specific facility.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

class OrbitCaseType(models.Model):
    PROCEDURE_TYPE_DIAGNOSTIC = 0
    PROCEDURE_TYPE_INTERVENTION = 1
    PROCEDURE_TYPE_CHOICES = (
        (PROCEDURE_TYPE_DIAGNOSTIC, 'Diagnostic'),
        (PROCEDURE_TYPE_INTERVENTION, 'Intervention'),
    )
    procedure_type= models.IntegerField(
        default=1,
        choices=PROCEDURE_TYPE_CHOICES,
        help_text='Procedure type'
    )
    program_type = models.ForeignKey(ResidencyProgramType, null=False, on_delete=models.CASCADE, help_text='Training program for this goal.')
    subspecialty = models.ForeignKey(SubSpecialty, null=False, on_delete=models.CASCADE, help_text='Subspecialty.')
    procedure = models.ForeignKey(OrbitProcedure, null=False, on_delete=models.CASCADE, help_text='Procedure reference for this goal.')
    goal_value = models.IntegerField(default=0, help_text="Goal value.")

    class Meta:
        unique_together = ('program_type', 'procedure_type', 'subspecialty', 'procedure')

class CaseManager(models.Manager):

    def re_match(self, facility = None, force_match = False):
        procedure_regex_dict = {}
        proc_match_qset = OrbitProcedureMatch.objects.all()
        # prepare a mapping of facility to dict of regexps
        # like: { 'UAMS': {'regex1': OrbitProcedureMatch1, 'regex2': OrbitProcedureMatch2 } }
        if facility:
            proc_match_qset = proc_match_qset.filter(facility__iexact=facility)
            procedure_regex_dict = { facility : {p.regex:p for p in proc_match_qset} }
        else:
            for p in proc_match_qset:
                procedure_regex_dict.setdefault(p.facility, {}).update({p.regex:p})

        if len(proc_match_qset) == 0:
            logger.info("[CaseLogIngest] No procedure matches for provided facility: {}, quit".format(facility))
            return False

        case_qset = Case.objects.all()
        if not force_match:
            case_qset = case_qset.filter(procedure__isnull=True)
        if facility:
            case_qset = case_qset.filter(facility__iexact=facility)

        logger.info('[CaseLogIngest] Num cases to ingest Orbit Case Types: {0}'.format(len(case_qset)))

        updated = []
        for case in case_qset:
            # get all regexp's for this case facility
            rx_matches = procedure_regex_dict.get(case.facility)
            procedure_match_regex = next((rx for rx in rx_matches if re.match(rx, case.procedure_name)), None)
            if procedure_match_regex:
                with transaction.atomic():
                    case.procedure = rx_matches[procedure_match_regex].procedure
                    case.save(update_fields=('procedure','modified',))
                    updated.append(case)

        logger.info('[CaseLogIngest] Num cases matched new Orbit Case Types: {0}'.format(len(updated)))
        return True

class Case(models.Model):
    npi = models.CharField(max_length=20, null=False, unique=False, help_text='NPI number of the resident.')
    cpt_code = models.CharField(max_length=50, null=False, unique=False, help_text='CPT code of the procedure.')
    procedure = models.ForeignKey(OrbitProcedure, null=True, on_delete=models.PROTECT, help_text='Procedure reference for this case.')
    procedure_name = models.CharField(max_length=250, null=False, unique=False, help_text='Procedure name as provided by facility.')
    profile = models.ForeignKey(Profile,
                                on_delete=models.CASCADE,
                                related_name='cases',
                                db_index=True,
                                help_text='Internal resident profile ID.',
                                blank=True,
                                )
    timestamp = models.DateTimeField(null=False, help_text='Date and time of the actual procedure.')
    age_category = models.CharField(null=False, max_length=60, help_text='Patient category: child or adult.')
    facility = models.CharField(null=False, max_length=100, help_text='Facility.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    objects = CaseManager()

    class Meta:
        unique_together = ('npi', 'cpt_code', 'timestamp')
