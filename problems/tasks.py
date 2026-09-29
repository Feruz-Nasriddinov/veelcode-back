from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from .models import Problem
from .services.evaluators import evaluate
from users.models import Submission

from .services.evaluators import ContainerInfraError
from .services.evaluators.cleanup import remove_expired
import logging

logger = logging.getLogger(__name__) 

@shared_task(bind=True, max_retries=5, default_retry_delay=1)
def evaluate_tasks(self, submission_id, files):
    try:
        submission = Submission.objects.get(id=submission_id)
    except Submission.DoesNotExist as exc:
        raise self.retry(exc=exc)

    try:
        result = evaluate(files, submission.problem_id)
        if result.get('status') == 'timeout':
            submission.status, submission.error_message = 'failed', 'Evaluation timed out'
        elif result.get('status') == 'out_of_memory':
            submission.status, submission.error_message = 'failed', 'Submission ran out of memory'
        elif result.get('status') == 'no_tests':
            submission.status, submission.error_message = 'failed', 'Problem has no hidden tests'
        elif result.get('status') == 'unsupported':
            submission.status, submission.error_message = 'failed', 'Unsupported problem type'
        elif result.get('status') == 'app_failed':
            submission.status, submission.error_message = 'failed', 'App did not start'
        elif result.get('status') == 'failed':
            submission.status, submission.error_message = 'failed', 'Internal error happened'
        else:
            submission.status, submission.score = 'done', result.get('percentage')

    except ContainerInfraError as exc:
        if self.request.retries >= self.max_retries:
            submission.status, submission.error_message = 'failed', 'Infra error after retries'
            submission.save(update_fields=['status', 'error_message'])
            return
        raise self.retry(exc=exc)

    except SoftTimeLimitExceeded:
        submission.status, submission.error_message = 'failed', 'Evaluation timed out'

    except Exception:
        logger.exception(f"Unhandled evaluation error for submission {submission_id}")
        submission.status, submission.error_message = 'failed', 'Internal error occurred'

    submission.save(update_fields=['status', 'score', 'error_message'])

@shared_task
def cleanup_evaluator_leftovers():
    return remove_expired()
