from rest_framework import serializers
from .models import UserDetail
from problems.serializers import ProblemSerializer

class UserDetailSerializer(serializers.ModelSerializer):
    problem = ProblemSerializer(read_only = True)

    class Meta:
        model = UserDetail
        fields = ['id', 'score', 'problem', 'status']