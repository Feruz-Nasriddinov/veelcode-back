from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import get_object_or_404

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import Submission, UserLocation
from .serializers import ProfileSerializer

def get_user_tz(user):

    try:
        name = user.location.timezone
    except UserLocation.DoesNotExist:
        name = "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'profile'

    def get(self, request):

        submissions = Submission.objects.filter(user = request.user).select_related('problem', 'user')

        serializer = ProfileSerializer(submissions, many=True)

        return Response(serializer.data)
    
MIN_YEAR = 2026

class ActivityView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'activity-track'

    def get(self, request):
        user_timezone = get_user_tz(request.user)

        current_year = timezone.localdate(timezone = user_timezone).year

        raw_year = request.query_params.get("year", current_year)
        try:
            year = int(raw_year)
        except (TypeError, ValueError):
            return Response({"detail": "year must be a number"}, status=400)

        if not MIN_YEAR <= year <= current_year:
            return Response(
                {"detail": f"year must be between {MIN_YEAR} and {current_year}"},
                status=400,
            )
        
        start = timezone.make_aware(datetime(year, 1, 1), user_timezone)
        end = timezone.make_aware(datetime(year + 1, 1, 1), user_timezone)

        rows = (
            Submission.objects
            .filter(user=request.user, created_at__gte=start, created_at__lt=end)
            .annotate(day=TruncDate("created_at", tzinfo=user_timezone))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        days = [{"date": r["day"].isoformat(), "count": r["count"]} for r in rows]

        return Response({
            "year": year,
            "total": sum(d["count"] for d in days),
            "days": days,
        })