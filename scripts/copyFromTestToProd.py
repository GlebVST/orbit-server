"""This requires a key called prod in settings.DATABASES containing the prod db, and default points to testdb."""
from users.models import *
# Used for one-time push to prod 02/18/19 only.
# PROD: state-abbrev => State instance
statesDict = {}
country_prod = Country.objects.using('prod').get(code=Country.USA)
states_prod = country_prod.states.all()
for state in states_prod:
    statesDict[state.abbrev] = state

# PROD: Specialty name  => PracticeSpecialty instance
specialtyDict = {}
specs = PracticeSpecialty.objects.using('prod').all()
for m in specs:
    specialtyDict[m.name] = m


def copyCmeTags():
    num_created = 0
    tags_test = CmeTag.objects.all().order_by('pk')
    for tag in tags_test:
        qs = CmeTag.objects.using('prod').filter(name__iexact=tag.name)
        if not qs.exists():
            tag_prod = CmeTag.objects.using('prod').create(
                    name=tag.name,
                    description=tag.description,
                    srcme_only=tag.srcme_only,
                    instructions=tag.instructions
                )
            print('Created tag_prod: {0} srcme_only: {0.srcme_only}'.format(tag_prod))
            num_created += 1
        else:
            tag_prod = qs[0]
            if tag_prod.name != tag.name:
                tag_prod.name = tag.name
            tag_prod.description = tag.description
            tag_prod.srcme_only = tag.srcme_only
            tag_prod.instructions = tag.instructions
            tag_prod.save()
            print('Updated tag_prod: {0} srcme_only: {0.srcme_only}'.format(tag_prod))
    return num_created

def copySubSpecs():
    num_created = 0
    subspecs_test = SubSpecialty.objects.select_related('specialty').all().order_by('pk')
    for m in subspecs_test:
        qs = SubSpecialty.objects.using('prod').select_related('specialty').filter(specialty__name=m.specialty.name, name=m.name)
        if not qs.exists():
            ps_prod = specialtyDict[m.specialty.name]
            m_prod = SubSpecialty.objects.using('prod').create(specialty=ps_prod, name=m.name)
            print('Created subspec_prod: {0.specialty}|{0.name}'.format(m_prod))
            num_created += 1
    return num_created

def copyStateTags():
    """Copy state.cmeTags, doTags, and StateDeatag"""
    num_created = 0
    tagsDict = {}
    tags_prod = CmeTag.objects.using('prod').all()
    for tag in tags_prod:
        tagsDict[tag.name] = tag
    country = Country.objects.get(code=Country.USA)
    states = country.states.all().order_by('abbrev')
    for state in states:
        state_prod = statesDict[state.abbrev]
        # cmeTags
        for tag in state.cmeTags.all():
            tag_prod = tagsDict[tag.name]
            state_prod.cmeTags.add(tag_prod)
            logger.info('State {0} cmeTag {1}'.format(state_prod, tag_prod))
        # doTags
        for tag in state.doTags.all():
            tag_prod = tagsDict[tag.name]
            state_prod.doTags.add(tag_prod)
            logger.info('State {0} doTag {1}'.format(state_prod, tag_prod))
        # StateDeatag
        dea_tags = StateDeatag.objects.select_related('tag').filter(state=state)
        for sd in dea_tags:
            tag_prod = tagsDict[sd.tag.name]
            sd_prod, created = StateDeatag.objects.using('prod').get_or_create(state=state_prod, tag=tag_prod, dea_in_state=sd.dea_in_state)
            if created:
                logger.info('Created StateDeatag {0} dea_in_state: {0.dea_in_state}'.format(sd_prod))
                num_created += 1
    return num_created # StateDeatag only
