from decimal import Decimal
import logging
from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription, CmeBoost, CmeBoostPurchase

logger = logging.getLogger('gen.psrl')

DISPLAY_PRICE_AS_MONTHLY = True

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    plan_type = serializers.StringRelatedField(read_only=True)
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, min_value=Decimal('0.01'))
    discountPrice = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False)
    displayMonthlyPrice = serializers.SerializerMethodField()
    plan_key = serializers.PrimaryKeyRelatedField(read_only=True)
    upgrade_plan = serializers.PrimaryKeyRelatedField(read_only=True)
    needs_payment_method = serializers.BooleanField(source='plan_type.needs_payment_method')

    def get_displayMonthlyPrice(self, obj):
        """Returns True if the price should be divided by 12 to be displayed as a monthly price."""
        return DISPLAY_PRICE_AS_MONTHLY

    class Meta:
        model = SubscriptionPlan
        fields = (
            'id',
            'planId',
            'plan_type',
            'plan_key',
            'display_name',
            'price',
            'discountPrice',
            'trialDays',
            'billingCycleMonths',
            'displayMonthlyPrice',
            'active',
            'upgrade_plan',
            'needs_payment_method',
            'maxCmeMonth',
            'maxCmeYear',
            'created',
            'modified'
        )

class SubscriptionPlanPublicSerializer(serializers.ModelSerializer):
    plan_type = serializers.StringRelatedField(read_only=True)
    plan_key = serializers.StringRelatedField(read_only=True)
    needs_payment_method = serializers.BooleanField(source='plan_type.needs_payment_method')
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    discountPrice = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False, read_only=True)
    displayMonthlyPrice = serializers.SerializerMethodField()

    def get_displayMonthlyPrice(self, obj):
        """Returns True if the price should be divided by 12 to be displayed as a monthly price."""
        return DISPLAY_PRICE_AS_MONTHLY

    class Meta:
        model = SubscriptionPlan
        fields = (
            'id',
            'planId',
            'plan_type',
            'plan_key',
            'display_name',
            'price',
            'discountPrice',
            'displayMonthlyPrice',
            'needs_payment_method',
            'trialDays',
            'billingCycleMonths',
        )


class CreateUserSubsSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all())
    payment_method_token = serializers.CharField(max_length=64)
    invitee_discount = serializers.BooleanField()
    convertee_discount = serializers.BooleanField()
    trial_duration = serializers.IntegerField(required=False)

    def save(self, **kwargs):
        """This expects user passed in to kwargs
        Call Manager method UserSubscription createBtSubscription
        with the following parameters:
            plan_id: planId of plan
            payment_method_token:str for Customer
            trial_duration:int number of days of trial (if not given, use plan default)
            invitee_discount:bool - used for InvitationDiscount
            convertee_discount:bool - used for AffiliatePayout
        Returns: tuple (result object, UserSubscription instance)
        """
        user = kwargs['user']
        validated_data = self.validated_data
        plan = validated_data['plan']
        payment_method_token = validated_data['payment_method_token']
        invitee_discount = validated_data['invitee_discount']
        convertee_discount = validated_data['convertee_discount']
        subs_params = {
            'plan_id': plan.planId,
            'payment_method_token': payment_method_token,
            'invitee_discount': invitee_discount,
            'convertee_discount': convertee_discount
        }
        key = 'trial_duration'
        test_code = user.profile.isForTestTransaction()
        if not test_code:
            if key in validated_data:
                subs_params[key] = validated_data[key]
            return UserSubscription.objects.createBtSubscription(user, plan, subs_params)
        else:
            # user is designated for testing payment transactions
            subs_params[key] = 1 # needed in order to test PASTDUE
            subs_params['code'] = test_code
            subs_params.pop('invitee_discount')
            subs_params.pop('convertee_discount')
            return UserSubscription.objects.createBtSubscriptionWithTestAmount(user, plan, subs_params)


class ActivatePaidUserSubsSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all())
    payment_method_token = serializers.CharField(max_length=64)

    def save(self, **kwargs):
        """This expects user_subs passed in to kwargs
        Call Manager method UserSubscription startActivePaidPlan
        Returns: tuple (result object, UserSubscription instance)
        """
        user_subs = kwargs['user_subs']
        validated_data = self.validated_data
        plan = validated_data['plan']
        payment_token = validated_data['payment_method_token']
        return UserSubscription.objects.startActivePaidPlan(user_subs, payment_token, plan)


class UpgradePlanSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all())
    payment_method_token = serializers.CharField(max_length=64)

    def save(self, **kwargs):
        """This expects user_subs passed into kwargs for the existing
        UserSubscription to be canceled.
        It calls UserSusbscription manager method upgradePlan.
        Returns: tuple (result object, UserSubscription instance)
        """
        user_subs = kwargs['user_subs'] # existing user_subs on old plan
        validated_data = self.validated_data
        plan = validated_data['plan']
        payment_method_token = validated_data['payment_method_token']
        return UserSubscription.objects.upgradePlan(user_subs, plan, payment_method_token)

class CmeBoostSerializer(serializers.ModelSerializer):
    credits = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = CmeBoost
        fields = (
            'id',
            'name',
            'credits',
            'price'
        )

class CmeBoostPurchaseSerializer(serializers.ModelSerializer):
    boost = serializers.PrimaryKeyRelatedField(
        queryset=CmeBoost.objects.all())
    payment_method_token = serializers.CharField(max_length=64)

    class Meta:
        model = CmeBoostPurchase
        fields = (
            'id',
            'boost',
            'payment_method_token',
            'created',
            'modified'
        )

    def save(self, **kwargs):
        """This expects user passed in to kwargs
        Call Manager method CmeBoostPurchase purchaseBoost
        with the following parameters:
            boost_id: reference to specific boost option
            payment_method_token:str for Customer
        Returns: result object
        """
        user = kwargs['user']
        validated_data = self.validated_data
        boost = validated_data['boost']
        payment_method_token = validated_data['payment_method_token']
        return CmeBoostPurchase.objects.purchaseBoost(user, boost, payment_method_token)
