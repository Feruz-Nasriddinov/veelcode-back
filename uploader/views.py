from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.throttling import ScopedRateThrottle

from problems.models import Problem, ProblemFile, UpdateProblem
from problems.serializers import (
    ProblemSerializer, ProblemFileUploadSerializer, ProblemFilesUploadSerializer,
    UpdateProblemSerializer, UpdateProblemReadSerializer,
)

from .services import add_problem_files
from problems.paginators import HistoryPagination
class UploadProblemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-problem'

    def post(self, request):
        serializer = ProblemSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(status='pending', created_by = request.user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

class UploadProblemDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'upload-files'

    def post(self, request, problem_id):

        problem = get_object_or_404(Problem, id = problem_id, created_by = request.user)

        if problem.status == 'accepted' or problem.status == 'rejected':
            return Response({"message": 'Cannot make changes to the accepted/rejected problems'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProblemFilesUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        files = add_problem_files(problem, serializer.validated_data)

        return Response(ProblemFileUploadSerializer(files, many=True).data, status=status.HTTP_201_CREATED)

class UpdateUploadedProblemView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'update-problem'

    def post(self, request, problem_file_id):
        problem_file = get_object_or_404(ProblemFile, id = problem_file_id, problem__created_by = request.user)

        serializer = UpdateProblemSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(problem = problem_file.problem, problem_file = problem_file)

        return Response({'message': 'Updates saved'}, status=status.HTTP_201_CREATED)

class UpdatesHistoryView(generics.ListAPIView):
    serializer_class = UpdateProblemReadSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = HistoryPagination
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'updates-history'

    def get_queryset(self):
        return UpdateProblem.objects.filter(problem__created_by = self.request.user).select_related('problem', 'problem_file').order_by('-created_at')