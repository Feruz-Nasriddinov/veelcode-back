from django.db import models
import uuid

class Problem(models.Model):
    CHOICES = [
        ('easy', 'easy'),
        ('medium', 'medium'),
        ('hard', 'hard')
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=True
    )
    title = models.CharField(max_length=300)
    description = models.CharField(500)
    difficulty = models.CharField(choices=CHOICES)

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
