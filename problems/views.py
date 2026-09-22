from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination

from .models import Problem
from .serializers import ProblemSerializer, ProblemWithFilesSerializer, SubmissionFilesSerializer
from .tasks import evaluate_tasks
from users.models import UserDetail
from users.serializers import UserDetailSerializer

class ProblemPagination(PageNumberPagination):
    max_page_size = 100
    page_size = 20

class ProblemListView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-problems'

    def get(self, request):

        problems = Problem.objects.filter(status='accepted').order_by('created_at')

        paginator = ProblemPagination()

        page = paginator.paginate_queryset(
            problems, 
            request,
            view=self
        )

        serializer = ProblemSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

class ProblemDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-content'

    def get(self, request, problem_id):

        problem = get_object_or_404(Problem, id=problem_id, status='accepted')

        serializer = ProblemWithFilesSerializer(problem)

        return Response(serializer.data)

class SubmitView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'submit'

    def post(self, request, problem_id):

        problem = get_object_or_404(Problem, id = problem_id)

        if problem.status != 'accepted':
            return Response({'message': 'Cannot submit on pending and rejected problems'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SubmissionFilesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        submission = UserDetail.objects.create(
                user = request.user,
                problem = problem,
                status = 'pending'
            )
        evaluate_tasks.apply_async(
            args=[submission.id, serializer.validated_data],
            time_limit = submission.problem.time_required + 20,
            soft_time_limit = submission.problem.time_required + 10,
        )

        return Response({'submission_id': submission.id, 'status': 'pending'}, status=status.HTTP_202_ACCEPTED)

class SubmissionDetailsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'submit-details'

    def get(self, request):

        submissions = UserDetail.objects.filter(user = request.user).select_related('problem')

        data = UserDetailSerializer(submissions, many=True).data

        return Response(data)