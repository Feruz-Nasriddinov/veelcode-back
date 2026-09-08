from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from .models import Problem, ProblemFile
from .serializers import ProblemFileSerializer, ProblemListSerializer, ProblemDetailSerializer
from users.models import UserDetail
from users.serializers import UserDetailSerializer

class ProblemListView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-problems'

    def get(self, request):

        problems = Problem.objects.all()

        serializer = ProblemListSerializer(problems, many=True)

        return Response(serializer.data)

class ProblemDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-content'

    def get(self, request, problem_id):

        problem = get_object_or_404(Problem, id=problem_id)

        serializer = ProblemDetailSerializer(problem)

        return Response(serializer.data)

class ScoreView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-score'

    def get(self, request, problem_id):

        user_detail = get_object_or_404(UserDetail, problem_id=problem_id, user=request.user)

        serializer = UserDetailSerializer(user_detail)

        return Response(serializer.data)