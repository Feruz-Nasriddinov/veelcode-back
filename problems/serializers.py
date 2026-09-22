from pathlib import PurePosixPath

from django.conf import settings
from rest_framework import serializers
from rest_framework.settings import api_settings

from .models import Problem, ProblemFile

class ProblemFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProblemFile
        fields = ['id', 'directory', 'content']
        read_only_fields = ['id']

class ProblemWithFilesSerializer(serializers.ModelSerializer):
    files = ProblemFileSerializer(many=True, read_only=True)

    class Meta:
        model = Problem
        fields = ['id', 'title', 'description', 'files', 'difficulty']

class ProblemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Problem
        fields = ['id', 'title', 'description', 'difficulty']
        read_only_fields = ['id']

class SubmissionFilesSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: [
                    'Expected an object mapping file paths to file contents.'
                ]}
            )
        if not data:
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: ['At least one file is required.']}
            )
        if len(data) > settings.SUBMISSION_MAX_FILES:
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: [
                    f'At most {settings.SUBMISSION_MAX_FILES} files are allowed.'
                ]}
            )

        errors = {}
        cleaned = {}
        total_bytes = 0

        for path, content in data.items():
            path_error = validate_submission_path(path)
            if path_error:
                errors[str(path)] = [path_error]
                continue
            if not isinstance(content, str):
                errors[path] = ['File content must be a string.']
                continue
            total_bytes += len(content.encode('utf-8'))
            cleaned[str(PurePosixPath(path))] = content

        if errors:
            raise serializers.ValidationError(errors)

        if total_bytes > settings.SUBMISSION_MAX_TOTAL_BYTES:
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: [
                    f'Submission is larger than the {settings.SUBMISSION_MAX_TOTAL_BYTES} byte limit.'
                ]}
            )

        return cleaned


def validate_submission_path(path):
    if not isinstance(path, str) or not path.strip():
        return 'File path must be a non-empty string.'
    if len(path) > settings.SUBMISSION_MAX_PATH_LENGTH:
        return f'File path is longer than {settings.SUBMISSION_MAX_PATH_LENGTH} characters.'
    if '\x00' in path:
        return 'File path may not contain null bytes.'
    if '\\' in path:
        return 'Use "/" as the path separator.'
    if path.startswith('/'):
        return 'File path must be relative.'
    parts = PurePosixPath(path).parts
    if '..' in parts:
        return 'File path may not contain "..".'
    if any(':' in part for part in parts):
        return 'File path may not contain ":".'
    return None
