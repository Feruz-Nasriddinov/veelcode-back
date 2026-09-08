from rest_framework import serializers
from .models import UserDetail

class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDetail
        fields = ['id', 'score']