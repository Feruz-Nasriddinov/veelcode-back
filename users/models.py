from django.db import models
from django.contrib.auth.models import User
from problems.models import Problem

class UserDetail(models.Model):
    CHOICES = [
        ('pending', 'pending'),
        ('running', 'running'),
        ('done', 'done'),
        ('failed', 'failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='details')
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name='details')
    score = models.IntegerField(default=0)
    status = models.CharField(choices=CHOICES)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f'{self.user.username}-{self.score}'