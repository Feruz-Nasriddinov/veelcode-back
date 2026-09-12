from rest_framework import serializers
from .models import Problem, ProblemFile

class ProblemFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProblemFile
        fields = ['id', 'directory', 'content']

class ProblemWithFilesSerializer(serializers.ModelSerializer):
    files = ProblemFileSerializer(many=True, read_only=True)

    class Meta:
        model = Problem
        fields = ['id', 'title', 'description', 'files', 'difficulty']

class ProblemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Problem
        fields = ['id', 'title', 'description', 'difficulty', 'time_required']