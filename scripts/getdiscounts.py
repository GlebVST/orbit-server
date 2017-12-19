from users.models import *
import calendar
from django.utils import timezone
from operator import itemgetter
from pprint import pprint
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal('.01')

def main():
    new_plan = SubscriptionPlan.objects.get(name='Plus')
    pd = Discount.objects.get(discountType=new_plan.planId, activeForType=True)
    now = timezone.now()
    daysInYear = 365 if not calendar.isleap(now.year) else 366
    profiles = Profile.objects.all().order_by('created')
    for p in profiles:
        u = p.user
        us = UserSubscription.objects.getLatestSubscription(u)
        if not us:
            continue
        if us.status != UserSubscription.ACTIVE:
            continue
        if us.display_status == UserSubscription.UI_TRIAL:
            owed = new_plan.discountPrice
            discounts = UserSubscription.objects.getDiscountsForNewSubscription(u)
            discount_amount = 0
            for d in discounts:
                owed -= d['discount']
                discount_amount += d['discount']
            print('User {0}|TRIAL|owed:{1}|discount:{2}'.format(u,
                owed.quantize(TWO_PLACES, ROUND_HALF_UP),
                discount_amount
            ))
            continue
        old_plan = us.plan
        if old_plan.name != 'Standard':
            continue
        td = now - us.billingStartDate
        billingDay = td.days
        owed, discount_amount = UserSubscription.objects.getDiscountAmountForUpgrade(old_plan, new_plan, us.billingCycle, billingDay, daysInYear)
        print('User:{0}|billingCycle:{1.billingCycle}|billingDay:{2}|owed:{3}|discount:{4}'.format(u, us, billingDay,
            owed.quantize(TWO_PLACES, ROUND_HALF_UP),
            discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP)
        ))
        # compare us.nextBillingAmount with old_plan.price
        if (old_plan.price > us.nextBillingAmount):
            # user has earned some discounts that would have been applied to the next billing cycle on their old plan
            earned_discount_amount = old_plan.price - us.nextBillingAmount
            # check if can apply the earned_discount_amount right now
            t = discount_amount + earned_discount_amount
            if t < new_plan.price:
                discount_amount = t
                owed -= earned_discount_amount
                print('-- Apply earned_discount={0}|New owed:{1}'.format(
                    earned_discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP),
                    owed.quantize(TWO_PLACES, ROUND_HALF_UP)
                ))
            else:
                # Defer the earned discount to the next billingCycle on the new subscription
                ead = earned_discount_amount.quantize(TWO_PLACES, ROUND_HALF_UP)
                print('-- Defer earned_discount={0} from user_subs {1.subscriptionId}'.format(ead, us))



def old():
    profiles = Profile.objects.all().order_by('created')
    for p in profiles:
        discounts = UserSubscription.objects.getDiscountsForNewSubscription(p.user)
        data = [{
            'discountId': d['discount'].discountId,
            'amount': d['discount'].amount,
            'discountType': d['discountType'],
            'displayLabel': d['displayLabel']
            } for d in discounts]
        # sort by amount desc
        display_data = sorted(data, key=itemgetter('amount'), reverse=True)
        if data:
            print('Discounts for {0}/{0}'.format(p.user.email, p.getFullName()))
            pprint(display_data)
            print(40*'-')
