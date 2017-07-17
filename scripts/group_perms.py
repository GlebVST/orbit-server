"""Functions to get & assign group permissions"""
from django.contrib.auth.models import User, Group, Permission
import json
from pprint import pprint

DEFAULT_FPATH = 'users/fixtures/natural_groupperms.json'

def getGroupPerms():
    groups = Group.objects.all().order_by('id')
    data = [dict(name=g.name, codenames=[p.codename for p in g.permissions.all().order_by('codename')]) for g in groups]
    pprint(data)
    return data

def writeGroupPerms(data, fpath=DEFAULT_FPATH):
    json_data = json.dumps(data)
    f = open(fpath, 'wb')
    f.write(json_data)
    f.close()

def readGroupPerms(fpath):
    f = open(fpath, 'rb')
    data = json.loads(f.read())
    f.close()
    return data

def assignGroupPerms(data):
    """Assign group permissions from data (overwrites any prev perms)
    Args:
        data:list of {name:str - group_name, codenames:list - list of permission codenames to assign to group}
    All groups and perms must already exist in db.
    """
    for d in data:
        group_name = d['name']
        codenames = d['codenames']
        g = Group.objects.get(name=group_name)
        perms = [Permission.objects.get(codename=c) for c in codenames]
        if perms:
            g.permissions.set(perms)
            print('Set permissions for {0.name}'.format(g))
