from rest_framework.test import APIClient


class SecureAPIClient(APIClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.defaults['HTTP_ORIGIN'] = 'https://testserver'

    def generic(self, method, path, *args, **kwargs):
        kwargs['secure'] = True
        return super().generic(method, path, *args, **kwargs)
