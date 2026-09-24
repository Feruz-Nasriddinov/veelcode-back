from rest_framework.generics import get_object_or_404

from problems.models import Problem

from .backend import DjangoEvaluator
from .base import ContainerInfraError, score_report
from .devops import DevOpsEvaluator
from .frontend import NextEvaluator, ReactEvaluator

EVALUATORS = {
    ('backend', 'django'): DjangoEvaluator,
    ('backend', 'django rest framework'): DjangoEvaluator,
    ('frontend', 'react'): ReactEvaluator,
    ('frontend', 'next.js'): NextEvaluator,
}

def get_evaluator(problem):
    if problem.field == 'devops':
        return DevOpsEvaluator(problem)
    evaluator_class = EVALUATORS.get((problem.field, problem.framework))
    return evaluator_class(problem) if evaluator_class else None

def evaluate(files, problem_id):
    problem = get_object_or_404(Problem, id=problem_id)
    evaluator = get_evaluator(problem)
    if evaluator is None:
        return {'percentage': 0, 'status': 'unsupported'}
    return evaluator.evaluate(files)
