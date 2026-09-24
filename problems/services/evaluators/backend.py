from .base import APP_PORT, Evaluator

class DjangoEvaluator(Evaluator):
    runner_image = 'django-evaluator'
    runner_mount_mode = 'rw'
    grader_image = 'veelcode-backend-grader'

    def runner_command(self):
        return [
            'bash', '-c',
            f'python manage.py migrate --noinput && '
            f'exec python manage.py runserver 0.0.0.0:{APP_PORT} --noreload',
        ]
