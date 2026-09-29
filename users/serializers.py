from rest_framework import serializers
from .models import Submission
from problems.serializers import ProblemSerializer

class UserDetailSerializer(serializers.ModelSerializer):
    problem = ProblemSerializer(read_only = True)

    class Meta:
        model = Submission
        fields = ['id', 'score', 'problem', 'status']