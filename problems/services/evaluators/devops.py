from .base import Evaluator

class DevOpsEvaluator(Evaluator):
    grader_image = 'veelcode-devops-grader'
    grader_mem_limit = '256m'
