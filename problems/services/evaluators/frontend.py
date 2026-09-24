from .base import APP_PORT, Evaluator

COPY_TO_WORKSPACE = 'find /app -mindepth 1 -maxdepth 1 ! -name node_modules -exec cp -r -t /work {} + && cd /work'

class FrontendEvaluator(Evaluator):
    runner_image = 'veelcode-frontend-runner'
    runner_mem_limit = '1g'
    runner_pids_limit = 256
    grader_image = 'veelcode-frontend-grader'
    grader_mem_limit = '1g'
    grader_pids_limit = 256

    def grader_args(self, app_url):
        return ['--base-url', app_url, '--browser', 'chromium']

class ReactEvaluator(FrontendEvaluator):
    def runner_command(self):
        return [
            'bash', '-c',
            f'{COPY_TO_WORKSPACE} && node_modules/.bin/vite build && '
            f'exec node /opt/veelcode/serve.js dist {APP_PORT}',
        ]

class NextEvaluator(FrontendEvaluator):
    def runner_command(self):
        return [
            'bash', '-c',
            f'{COPY_TO_WORKSPACE} && node_modules/.bin/next build && '
            f'exec node_modules/.bin/next start -H 0.0.0.0 -p {APP_PORT}',
        ]
