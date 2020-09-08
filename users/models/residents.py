import logging

from django.contrib.auth.models import User
from django.db import models

logger = logging.getLogger('gen.models')

class CaseTagCategory(models.Model):
    name = models.CharField(help_text='Case tag category name.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class ProcedureCode(models.Model):
    code = models.CharField(max_length=200, unique=True, help_text='Procedure code. Must be unique.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code

class Procedure(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text='Procedure name. Must be unique.')
    codes = models.ManyToManyField(ProcedureCode,
                                  blank=True,
                                  related_name='procedures',
                                  help_text='Procedure codes.'
                                  )
    tag_categories = models.ManyToManyField(CaseTagCategory,
                                   blank=True,
                                   related_name='procedures',
                                   help_text='Case tag categories that apply to this procedure.'
                                   )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Case(models.Model):
    user = models.ForeignKey(User,
                             on_delete=models.CASCADE,
                             related_name='cases',
                             db_index=True
                             )
    resident_id = models.CharField(help_text='External resident ID.')
    case_code = models.ForeignKey(ProcedureCode, null=False, on_delete=models.CASCADE, help_text='Case Code.')
    timestamp = models.DateTimeField(null=False, help_text='Date and time of the actual procedure.')
    age_category = models.CharField(null=False, max_length=60, help_text='Patient category: child or adult.')
    tagged = models.DateTimeField(null=True, help_text='Timestamp when resident tagged their case.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

class CaseTag(models.Model):
    case = models.ForeignKey(Case, related_name='tags', on_delete=models.CASCADE, help_text='Case reference.')
    category = models.ForeignKey(CaseTagCategory, on_delete=models.CASCADE, help_text='Tag category.')
    value = models.IntegerField(default=0, help_text="Selected tag value")
    timestamp = models.DateTimeField()
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

