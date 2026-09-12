from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from problems.models import Problem
from problems.serializers import ProblemSerializer, ProblemFileSerializer

class UploadProblemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request):
        serializer = ProblemSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(status='pending', created_by = request.user)

        return Response({'message': 'Uploaded Problem will be checked'}, status=status.HTTP_201_CREATED)

class UploadProblemContentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request, problem_id):
        problem = get_object_or_404(Problem, id = problem_id, created_by = request.data)

        serializer = ProblemFileSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(problem=problem)

        return Response(status=status.HTTP_201_CREATED)