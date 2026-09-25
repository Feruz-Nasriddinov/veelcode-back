from django.db import transaction
from django.db.models import Prefetch, F
from kombu.exceptions import OperationalError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination

from .models import Problem, ProblemFile, Comment, Like
from .serializers import ProblemSerializer, ProblemWithFilesSerializer, SubmissionFilesSerializer, WriteAndPatchCommentSerializer
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

        problems = Problem.objects.filter(status='accepted').order_by('-created_at')

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

        visible_files = Prefetch('files', queryset=ProblemFile.objects.filter(is_hidden=False))
        problem = get_object_or_404(
            Problem.objects.prefetch_related(visible_files), id=problem_id, status='accepted'
        )

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

        try:
            with transaction.atomic():
                submission = UserDetail.objects.create(
                        user = request.user,
                        problem = problem,
                        status = 'pending'
                    )
                evaluate_tasks.apply_async(
                    args=[submission.id, serializer.validated_data],
                    time_limit = problem.time_required + 20,
                    soft_time_limit = problem.time_required + 10,
                )
        except OperationalError:
            return Response(
                {'message': 'Evaluation queue is unavailable, try again shortly'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({'submission_id': submission.id, 'status': 'pending'}, status=status.HTTP_202_ACCEPTED)

class SubmissionDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'submit-details'

    def get(self, request, submission_id):

        submission = get_object_or_404(UserDetail, id = submission_id, user = request.user)

        serializer = UserDetailSerializer(submission)

        return Response(serializer.data)

class SubmissionHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'history'

    def get(self, request):

        submissions = UserDetail.objects.filter(user = request.user).select_related('problem').order_by('-created_at')# '-' for descending order

        data = UserDetailSerializer(submissions, many=True).data

        return Response(data)

class CommentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'comment'

    def post(self, request, problem_id):
        problem = get_object_or_404(Problem, id = problem_id)

        serializer = WriteAndPatchCommentSerializer(data = request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(user = request.user, problem = problem)

        return Response({'commented': True}, status=status.HTTP_201_CREATED)

class CommentPatchView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'comment'
    
    def patch(self, request, comment_id):
        comment = get_object_or_404(Comment, id = comment_id, user = request.user)

        serializer = WriteAndPatchCommentSerializer(comment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response({'message': 'Comment edited successfully'}, status=status.HTTP_200_OK)

class CommentDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'comment'
    
    def delete(self, request, comment_id):

        comment = get_object_or_404(Comment, id = comment_id, user = request.user)
        comment.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

class LikeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'like'

    def post(self, request, comment_id):
        comment = get_object_or_404(Comment, id = comment_id)

        _ , created = Like.objects.get_or_create(
            user = request.user,
            comment = comment
        )

        if created:
            Comment.objects.filter(id = comment_id).update(like_count = F('like_count') + 1)

        return Response({'liked': True}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

class UnlikeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'unlike'

    def delete(self, request, comment_id):

        comment = get_object_or_404(Comment, id = comment_id)

        deleted , _ = Like.objects.filter(
            user = request.user,
            comment = comment
        ).delete()

        if deleted:
            Comment.objects.filter(id = comment_id).update(like_count = F('like_count') - 1)

        return Response(status=status.HTTP_204_NO_CONTENT)