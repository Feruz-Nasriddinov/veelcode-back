from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from .models import Problem
from .services.evaluator import evaluate
from users.models import UserDetail

from .services.evaluator import ContainerInfraError
import logging

logger = logging.getLogger(__name__) 

@shared_task(bind=True, max_retries=5, default_retry_delay=1)
def evaluate_tasks(self, submission_id, files):
    try:
        submission = UserDetail.objects.get(id=submission_id)
    except UserDetail.DoesNotExist as exc:
        raise self.retry(exc=exc)

    try:
        result = evaluate(files, submission.problem_id)
        if result.get('status') == 'timeout':
            submission.status, submission.error_message = 'failed', 'Evaluation timed out'
        elif result.get('status') == 'out_of_memory':
            submission.status, submission.error_message = 'failed', 'Submission ran out of memory'
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
