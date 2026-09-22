from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from .models import Problem
from .services.evaluator import evaluate
from users.models import UserDetail

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
        elif result.get('status') == 'failed':
            submission.status, submission.error_message = 'failed', 'Internal error happened'#vague, needs fixing later
        else:
            percentage = result.get('percentage')
            submission.status, submission.score = 'done', percentage
    except SoftTimeLimitExceeded:
        submission.status, submission.error_message = 'failed', 'Evaluation timed out'
    except Exception as e:
        submission.status, submission.error_message = 'failed', str(e)

    submission.save(update_fields=['status', 'score', 'error_message'])
