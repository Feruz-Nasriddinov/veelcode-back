from django.contrib import admin
from .models import Problem, ProblemFile, UpdateProblem

admin.site.register(Problem)
admin.site.register(ProblemFile)
admin.site.register(UpdateProblem)