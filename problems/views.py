from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from .models import Problem, ProblemFile
from .serializers import ProblemFileSerializer, ProblemListSerializer, ProblemDetailSerializer

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