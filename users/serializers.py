from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import *

# http://www.django-rest-framework.org/tutorial/5-relationships-and-hyperlinked-apis/
#class UserSerializer(serializers.HyperlinkedModelSerializer):
#    class Meta:
#        model = User
#        fields = ('url', 'id', 'username', 'email', 'groups')


class PPOSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointPurchaseOption
        fields = ('id', 'points', 'price', 'created', 'modified')


class DegreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Degree
        fields = ('id', 'abbrev', 'name', 'created', 'modified')

class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    degrees = serializers.PrimaryKeyRelatedField(
        queryset=Degree.objects.all(),
        many=True,
        allow_null=True
    )

    class Meta:
        model = Profile
        fields = (
            'id',
            'firstName',
            'lastName',
            'jobTitle',
            'description',
            'npiNumber',
            'socialUrl',
            'pictureUrl',
            'degrees',
            'created',
            'modified'
        )


class CustomerSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='user.id', read_only=True)
    # TODO: balance is a read_only field
    class Meta:
        model = Customer
        fields = (
            'id',
            'customerId',
            'contactEmail',
            'created',
            'modified'
        )
