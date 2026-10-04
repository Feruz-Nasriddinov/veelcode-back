import re
import uuid

from django.test import TestCase

from uploader.views import UpdateUploadedProblemView


class UploaderRoutingTests(TestCase):
    def test_uploader_urlconf_uses_the_name_django_expects(self):
        import uploader.urls

        self.assertTrue(
            hasattr(uploader.urls, 'urlpatterns'),
            'uploader/urls.py defines url_patterns; include() only reads urlpatterns',
        )

    def test_upload_endpoints_are_reachable_in_the_real_urlconf(self):
        from django.urls import Resolver404, resolve

        try:
            resolve('/api/uploader/problem/')
        except Resolver404:
            self.fail('uploader views are not wired into config/urls.py')

    def test_update_endpoint_is_wired_to_the_update_view(self):
        import uploader.urls

        routes = [
            p for p in uploader.urls.urlpatterns
            if getattr(p.callback, 'view_class', None) is UpdateUploadedProblemView
        ]

        self.assertEqual(len(routes), 1)
        self.assertEqual(set(routes[0].pattern.converters), {'problem_file_id'})
        self.assertTrue(
            re.fullmatch(routes[0].pattern.converters['problem_file_id'].regex, str(uuid.uuid4())),
            'problem_file_id must accept a UUID ProblemFile id',
        )

    def test_update_problem_throttle_scope_has_a_rate(self):
        from django.conf import settings

        self.assertIn(
            UpdateUploadedProblemView.throttle_scope,
            settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'],
        )
