from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from .models import Problem
from .serializers import ProblemSerializer, ProblemWithFilesSerializer
from .tasks import evaluate_tasks
from users.models import UserDetail
from users.serializers import UserDetailSerializer

class ProblemListView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-problems'

    def get(self, request):

        problems = Problem.objects.all()

        serializer = ProblemSerializer(problems, many=True)

        return Response(serializer.data)

class ProblemDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-content'

    def get(self, request, problem_id):

        problem = get_object_or_404(Problem, id=problem_id)

        serializer = ProblemWithFilesSerializer(problem)

        return Response(serializer.data)

class ScoreView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'send-score'

    def get(self, request, problem_id):

        user_detail = UserDetail.objects.filter(problem_id=problem_id, user=request.user).select_related('problem')

        serializer = UserDetailSerializer(user_detail)

        return Response(serializer.data)

class SubmitView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'submit'

    def post(self, request, problem_id):

        problem = get_object_or_404(Problem, id = problem_id)

        submission = UserDetail.objects.create(
                user = request.user,
                problem = problem,
                status = 'pending'
            )
        evaluate_tasks.delay(submission.id, request.data)

        return Response({'submission_id': submission.id, 'status': 'pending'}, status=status.HTTP_202_ACCEPTED)

class SubmissionDetailsView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'submission-details'

    def get(self, request, submission_id):

        submission = get_object_or_404(UserDetail.objects.select_related('problem'), id = submission_id, user = request.user)

        data = UserDetailSerializer(submission).data

        return Response(data)