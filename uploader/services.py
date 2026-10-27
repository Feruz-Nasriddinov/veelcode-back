from django.conf import settings
from django.db import transaction
from django.db.models.functions import Length
from rest_framework import serializers

from problems.models import Problem, ProblemFile
from problems.serializers import path_collisions, printable


@transaction.atomic
def add_problem_files(problem, files):
    problem = Problem.objects.select_for_update().get(id=problem.id)
    stored = dict(problem.files.values_list('directory', Length('content')))

    if len(stored) + len(files) > settings.PROBLEM_MAX_FILES:
        raise serializers.ValidationError(
            {'message': f'A problem can have at most {settings.PROBLEM_MAX_FILES} files'}
        )
    new_chars = sum(len(file['content']) for file in files.values())
    if sum(stored.values()) + new_chars > settings.PROBLEM_MAX_TOTAL_CHARS:
        raise serializers.ValidationError(
            {'message': f'A problem can hold at most {settings.PROBLEM_MAX_TOTAL_CHARS} characters of files'}
        )

    errors = {}
    for path in path_collisions(stored.keys() | files.keys()) & files.keys():
        errors[printable(path)] = ['A file and a folder cannot share the same path.']
    for path in stored.keys() & files.keys():
        errors[printable(path)] = ['A file with this path already exists.']
    if errors:
        raise serializers.ValidationError(errors)

    return ProblemFile.objects.bulk_create(
        ProblemFile(problem=problem, directory=path, **file) for path, file in files.items()
    )
