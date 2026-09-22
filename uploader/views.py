from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from django.utils import timezone

from problems.models import Problem
from problems.serializers import ProblemSerializer, ProblemFileSerializer

class UploadProblemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request):
        serializer = ProblemSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(status='pending', created_by = request.user, created_at = timezone.now())

        return Response({'message': 'Uploaded Problem will be checked'}, status=status.HTTP_201_CREATED)

class UploadProblemDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request, problem_id):

        problem = get_object_or_404(Problem, id = problem_id, created_by = request.user)

        if problem.status == 'accepted':
            return Response({"message": 'Cannot make changes to the accepted problems'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProblemFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(problem=problem)

        return Response(status=status.HTTP_201_CREATED)