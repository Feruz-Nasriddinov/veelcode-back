from rest_framework import serializers
from .models import Submission
from problems.serializers import ProblemSerializer

class SubmissionSerializer(serializers.ModelSerializer):
    problem = ProblemSerializer(read_only = True)

    class Meta:
        model = Submission
        fields = ['id', 'score', 'problem', 'status']

class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source = 'user.username', read_only=True)
    language = serializers.CharField(source = 'problem.language', read_only=True)
    framework = serializers.CharField(source = 'problem.framework', read_only=True)
    difficulty = serializers.CharField(source = 'problem.difficulty', read_only=True)

    class Meta:
        model = Submission
        fields = ['id', 'username', 'language', 'framework', 'difficulty', 'score']