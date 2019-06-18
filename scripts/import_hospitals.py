from __future__ import unicode_literals
import csv
from collections import defaultdict
from django.db.models import Q
from users.models import Country, State, Hospital
from pprint import pprint
from operator import itemgetter

APOSTROPHE = "\u2019"

def clean_name(name):
    n2 = name.decode('utf_8')
    if APOSTROPHE in n2:
        n2 = n2.replace(APOSTROPHE, "'")
        return n2
    return name

def make_title(s):
    L = s.split()
    L2 = [v.title() for v in L]
    return ' '.join(L2)

def format_as_title():
    qset = Hospital.objects.all().select_related('state').order_by('name', 'city','state')
    data = []
    for m in qset:
        cleaned_city = make_title(m.city)
        cleaned_name = make_title(m.name)
        d = dict(state=m.state.name, city=cleaned_city, name=cleaned_name)
        d['id'] = m.pk
        data.append(d)
    fieldnames = ('id','name','city','state')
    with open('./scripts/hospitals_v1.csv', 'w') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in data:
            writer.writerow(d)
    print('done')

def inspect():
    f = open('./scripts/US_hospitals.csv', 'rb')
    reader = csv.DictReader(f)
    data = [row for row in reader]
    print('Num rows: {0}'.format(len(data)))
    f.close()
    names = []
    for d in data:
        name = clean_name(d['NAME'].strip())
        names.append({
            'name': name,
            'len_name': len(name)
        })
    names.sort(key=itemgetter('len_name'), reverse=True)
    for d in names[0:10]:
        print(d)
    return names

def name_histo():
    """Histo of first two letters"""
    qset = Hospital.objects.all().order_by('name', 'id')
    histo = dict()
    for m in qset:
        name = m.name
        first_letter = name[0]; second_letter = name[1]
        if first_letter not in histo:
            histo[first_letter] = {second_letter: [name,]}
        else:
            d = histo[first_letter]
            if second_letter not in d:
                d[second_letter] = [name,]
            else:
                d[second_letter].append(name)
    # count values in each bin
    for first_letter in sorted(histo):
        print("{0}".format(first_letter))
        d = histo[first_letter]
        for second_letter in d:
            names = d[second_letter]
            num_names = len(names)
            print("  {0}: {1}".format(second_letter, num_names))
    return histo

def clean_dups(name, data):
    """Append city,state abbrev to display_name"""
    # update display_name
    for m in data:
        m.display_name = "{0.name} - {0.city},{0.state.abbrev}".format(m)
        m.save()
        print(m.display_name)

def find_dups():
    qset = Hospital.objects.all().select_related('state').order_by('id')
    namedict = defaultdict(list)
    for m in qset:
        namedict[m.name].append(m)
    dups = dict()
    for name in sorted(namedict):
        if len(namedict[name]) > 1:
            dups[name] = namedict[name]
    for name in sorted(dups):
        clean_dups(name, dups[name])
        print(30*'-')
    print('len dups: {0}'.format(len(dups)))


def main():
    f = open('./scripts/US_hospitals.csv', 'rb')
    reader = csv.DictReader(f)
    data = [row for row in reader]
    print('Num rows: {0}'.format(len(data)))
    f.close()
    states_by_abbrev = dict()
    states = State.objects.all()
    for m in states:
        states_by_abbrev[m.abbrev] = m
    for d in data:
        state_abbrev = d['STATE'].strip()
        if state_abbrev in ('PR','AS','GU','MP','PW','VI'):
            continue
        status = d['STATUS'].strip()
        if status == 'CLOSED':
            continue
        name = clean_name(d['NAME'].strip())
        city = d['CITY'].strip()
        county = d['COUNTY'].strip()
        website = d['WEBSITE'].strip()
        try:
            state = states_by_abbrev[state_abbrev]
        except KeyError as e:
            print('KeyError: {0}'.format(str(e)))
            continue
        else:
            qset = Hospital.objects.filter(state=state, city=city, name=name) # uniq constraint
            display_name = "{0}, {1}".format(name, state_abbrev)
            if not qset.exists():
                h = Hospital.objects.create(
                        state=state,
                        name=name,
                        display_name=display_name,
                        city=city,
                        county=county,
                        website=website
                )
                try:
                    print('Created {0} in {0.state}'.format(h))
                except UnicodeDecodeError:
                    print('ID {0.pk} in {0.state}/{0.city} has non-ascii chars'.format(h))
    print('done')
    return data

def old_search(search_term):
    base_qs = Hospital.objects.select_related('state')
    qs_all = base_qs.annotate(
            search=SearchVector('name','city', 'state__name', 'state__abbrev')).all()
    qs_loc = base_qs.annotate(
            search=SearchVector('city', 'state__name', 'state__abbrev')).all()
    L = search_term.split(' in ')
    if len(L) > 1: # e.g. "holy cross in los angeles"
        qs1 = qs_all.filter(search=L[0])
        qs1_ids = set([m.id for m in qs1])
        qs2 = qs_loc.filter(search=L[-1])
        qs2_ids = set([m.id for m in qs2])
        common_ids = qs1_ids.intersection(qs2_ids)
        qset = base_qs.filter(id__in=list(common_ids))
    else:
        return qset.order_by('name','city')
