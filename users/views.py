from django.contrib.auth.models import User, Group
from rest_framework import generics, permissions, viewsets
from oauth2_provider.ext.rest_framework import TokenHasReadWriteScope, TokenHasScope
# app
from .serializers import *

# Degree
class DegreeList(generics.ListCreateAPIView):
    queryset = Degree.objects.all().order_by('abbrev')
    serializer_class = DegreeSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

class DegreeDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Degree.objects.all()
    serializer_class = DegreeSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

# PointPurchaseOption
class PPOList(generics.ListCreateAPIView):
    queryset = PointPurchaseOption.objects.all().order_by('points')
    serializer_class = PPOSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]

class PPODetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = PointPurchaseOption.objects.all()
    serializer_class = PPOSerializer
    permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]


# ------------------------------------------------------------------------
# from DRF tutorial
#class UserViewSet(viewsets.ModelViewSet):
#    """
#    API endpoint that allows users to be viewed or edited.
#    """
#    permission_classes = [permissions.IsAdminUser, TokenHasReadWriteScope]
#    #permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
#    queryset = User.objects.all().order_by('-date_joined')
#    serializer_class = UserSerializer

#class GroupViewSet(viewsets.ModelViewSet):
#    """
#    API endpoint that allows groups to be viewed or edited.
#    """
#    permission_classes = [permissions.IsAdminUser, TokenHasScope]
#    required_scopes = ['groups',]
#    queryset = Group.objects.all()
#    serializer_class = GroupSerializer
