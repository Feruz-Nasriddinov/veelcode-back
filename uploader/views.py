from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import Length
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from problems.models import Problem, ProblemFile, UpdateProblem
from problems.serializers import ProblemSerializer, ProblemFileUploadSerializer, UpdateProblemSerializer

class UploadProblemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request):
        serializer = ProblemSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(status='pending', created_by = request.user)

        return Response({'message': 'Uploaded Problem will be checked'}, status=status.HTTP_201_CREATED)

class UploadProblemDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request, problem_id):

        problem = get_object_or_404(Problem, id = problem_id, created_by = request.user)

        if problem.status == 'accepted' or problem.status == 'rejected':
            return Response({"message": 'Cannot make changes to the accepted problems'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProblemFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usage = problem.files.aggregate(count=Count('id'), chars=Sum(Length('content')))
        if usage['count'] >= settings.PROBLEM_MAX_FILES:
            return Response(
                {'message': f'A problem can have at most {settings.PROBLEM_MAX_FILES} files'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (usage['chars'] or 0) + len(serializer.validated_data['content']) > settings.PROBLEM_MAX_TOTAL_CHARS:
            return Response(
                {'message': f'A problem can hold at most {settings.PROBLEM_MAX_TOTAL_CHARS} characters of files'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save(problem=problem)

        return Response(status=status.HTTP_201_CREATED)

class UpdateUploadedProblemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'update-problem'

    def post(self, request, problem_file_id):
        problem_file = get_object_or_404(ProblemFile, id = problem_file_id, problem__created_by = request.user)

        serializer = UpdateProblemSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(problem = problem_file.problem, problem_file = problem_file)

        return Response({'message': 'Updates saved'}, status=status.HTTP_201_CREATED)