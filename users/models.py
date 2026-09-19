from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from problems.models import Problem
import uuid

username_validator = RegexValidator(
    regex=r'^[\w.+-]+\Z',
    message='Username may contain letters, digits and . + - _ only. "@" is not allowed.',
)

class User(AbstractUser):
    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[username_validator],
        error_messages={'unique': 'A user with that username already exists.'},
    )
    email = models.EmailField(unique=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower('username'), name='user_username_lower_unique'),
            models.UniqueConstraint(Lower('email'), name='user_email_lower_unique'),
        ]

class UserDetail(models.Model):
    CHOICES = [
        ('pending', 'pending'),
        ('running', 'running'),
        ('done', 'done'),
        ('failed', 'failed'),
    ]
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=True
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='details')
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name='details')
    score = models.IntegerField(default=0)
    status = models.CharField(choices=CHOICES, max_length=7)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f'{self.user.username}-{self.score}'
