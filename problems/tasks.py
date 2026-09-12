from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from services.evaluator import evaluate
from users.models import UserDetail
import xml.etree.ElementTree as ET

#the time limit should be changed after testing how long a typical docker test running would take
@shared_task(time_limit = 120, soft_time_limit = 110)
def evaluate_tasks(submission_id, files):
    submission = UserDetail.objects.get(id=submission_id)
    submission.status = 'running'
    submission.save(update_fields=['status'])

    try:
        result = evaluate(files)
        percentage = result.get('percentage')
        submission.status, submission.score = 'done', percentage
    except SoftTimeLimitExceeded:
        submission.status, submission.error_message = 'failed', 'Evaluation timed out'
    except Exception as e:
        submission.status, submission.error_message = 'failed', str(e)

    submission.save(update_fields=['status', 'score', 'error_message'])