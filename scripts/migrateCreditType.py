from users.models import *

def main():
    c1 = CreditType.objects.get(sort_order=1)
    c_other = CreditType.objects.get(sort_order=6)
    etypes = EntryType.objects.filter(name__in=['browser-cme','sr-cme'])
    qset = Entry.objects.filter(entryType__in=etypes).order_by('id')
    for m in qset:
        if m.ama_pra_catg == '1':
            m.creditType = c1
        elif m.ama_pra_catg == '0':
            m.creditType = c_other
        if m.creditType:
            m.save(update_fields=('creditType',))
