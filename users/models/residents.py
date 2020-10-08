import logging

from django.contrib.auth.models import User
from django.db import models

from users.models import SubSpecialty

logger = logging.getLogger('gen.models')

class TrainingProgramType(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text='Training program type. Must be unique.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class TrainingProgram(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text='Training program type. Must be unique.')
    program_type = models.ForeignKey(TrainingProgramType, null=False, on_delete=models.PROTECT, help_text='Training program type.')
    start_date = models.DateTimeField(null=True, help_text='Start of the program.')
    end_date = models.DateTimeField(null=True, help_text='End of the program.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Procedure(models.Model):
    PROCEDURE_TYPE_DIAGNOSTIC = 0
    PROCEDURE_TYPE_INTERVENTION = 1
    PROCEDURE_TYPE_CHOICES = (
        (PROCEDURE_TYPE_DIAGNOSTIC, 'Diagnostic'),
        (PROCEDURE_TYPE_INTERVENTION, 'Intervention'),
    )
    name = models.CharField(max_length=200, unique=True, help_text='Orbit Procedure name. Must be unique.')
    type= models.IntegerField(
        default=1,
        choices=PROCEDURE_TYPE_CHOICES,
        help_text='Procedure type'
    )
    regex = models.CharField(max_length=500, unique=True, help_text='Procedure name regex and synonyms.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class TrainingGoal(models.Model):
    program_type = models.ForeignKey(TrainingProgramType, null=False, on_delete=models.CASCADE, help_text='Training program for this goal.')
    subspecialty = models.ForeignKey(SubSpecialty, null=False, on_delete=models.CASCADE, help_text='Subspecialty.')
    procedure = models.ForeignKey(Procedure, null=False, on_delete=models.CASCADE, help_text='Procedure reference for this goal.')
    value = models.IntegerField(default=0, help_text="Goal value.")

    class Meta:
        unique_together = ('program_type', 'subspecialty', 'procedure')


class Case(models.Model):
    npi = models.CharField(max_length=20, unique=True, help_text='NPI number of the resident.')
    cpt_code = models.CharField(max_length=50, unique=True, help_text='CPT code of the procedure.')
    procedure = models.ForeignKey(Procedure, null=False, on_delete=models.PROTECT, help_text='Procedure reference for this case.')
    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             related_name='cases',
                             db_index=True,
                             help_text='Internal resident user ID.'
                             )
    timestamp = models.DateTimeField(null=False, help_text='Date and time of the actual procedure.')
    age_category = models.CharField(null=False, max_length=60, help_text='Patient category: child or adult.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
