from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView


class ProbeView(APIView):
    def post(self, request):
        return Response({'user': request.user.username})

    def get(self, request):
        return Response({'user': request.user.username})


urlpatterns = [
    path('api/auth/', include('authentication.urls')),
    path('api/probe/', ProbeView.as_view()),
]
