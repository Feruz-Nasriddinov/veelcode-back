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
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=True
    )
    title = models.CharField(max_length=300)
    description = models.CharField(500)
    difficulty = models.CharField(choices=DIFFICULTY_CHOICES)
    time_required = models.IntegerField(default=120)
    status = models.CharField(choices=STATUS_CHOICES)

    def __str__(self):
        return self.title

class ProblemFile(models.Model):
    problem = models.ForeignKey(
        Problem,
        on_delete=models.CASCADE,
        related_name='files'
    )
    directory = models.CharField(max_length=255)
    content = models.TextField()

    def __str__(self):
        return f'{self.problem.title}-{self.directory}'
