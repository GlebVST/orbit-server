import csv
from users.models import Country, State, Hospital
from pprint import pprint
from operator import itemgetter

APOSTROPHE = u"\u2019"

def clean_name(name):
    n2 = name.decode('utf_8')
    if APOSTROPHE in n2:
        n2 = n2.replace(APOSTROPHE, "'")
        return n2
    return name

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
        except KeyError, e:
            print('KeyError: {0}'.format(str(e)))
            continue
        else:
            qset = Hospital.objects.filter(state=state, city=city, name=name) # uniq constraint
            if not qset.exists():
                h = Hospital.objects.create(
                        state=state,
                        name=name,
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
