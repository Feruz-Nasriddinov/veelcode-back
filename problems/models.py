from django.conf import settings
from django.db import models
import uuid

class Problem(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'easy'),
        ('medium', 'medium'),
        ('hard', 'hard')
    ]

    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('accepted', 'accepted'),
        ('rejected', 'rejected')
    ]

    FIELD_CHOICES = [
        ('backend', 'backend'),
        ('frontend', 'frontend'),
        ('devops', 'devops')
    ]

    LANGUAGE_CHOICES = [
        ('python', 'python'),
        ('javascript', 'javascript'),
        ('typescript', 'typescript'),
        ('golang', 'golang'),
        ('java', 'java'),
    ]

    FRAMEWORK_CHOICES = [
        ('django', 'django'),
        ('django rest framework', 'django rest framework'),
        ('react', 'react'),
        ('next.js', 'next.js'),
        ('spring boot', 'spring boot'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=True
    )
    title = models.CharField(max_length=300)
    description = models.CharField(max_length=500)
    difficulty = models.CharField(choices=DIFFICULTY_CHOICES, max_length=6)
    time_required = models.IntegerField(default=0)
    status = models.CharField(choices=STATUS_CHOICES, max_length=8, default='pending')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)#this part means, when building the auth, deletion of accounts should be impossible and only the name and the email should be removed
                                                                  #while this field points to something real
    created_at = models.DateTimeField(auto_now_add=True)
    field = models.CharField(choices=FIELD_CHOICES, max_length=8)
    language = models.CharField(choices=LANGUAGE_CHOICES, max_length=10)
    framework = models.CharField(choices=FRAMEWORK_CHOICES, max_length=50)
    submission_count = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.title}-{self.difficulty}"

class ProblemFile(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=True
    )
    problem = models.ForeignKey(
        Problem,
        on_delete=models.CASCADE,
        related_name='files'
    )
    directory = models.CharField(max_length=255)
    content = models.TextField()
    is_hidden = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.problem.title}-{self.directory}'

class UpdateProblem(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    problem_file = models.ForeignKey(ProblemFile, on_delete=models.CASCADE)
    new_content = models.TextField()

    def __str__(self):
        return f'{self.problem.id}-{self.problem_file.directory}'

class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name='comments')
    text = models.CharField(max_length=1000)
    like_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['problem', '-created_at'])
        ]

    def __str__(self):
        return f"{self.user.username if self.user else '[deleted]'}-{self.text}"

class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields= ['user', 'comment'],
                name = 'unique_user_comment_like'
            )
        ]

    def __str__(self):
        return f"{self.user.username if self.user else '[deleted]'}-{self.created_at}"