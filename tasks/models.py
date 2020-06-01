from django.db import models


class User(models.Model):
    name = models.CharField(max_length=100)
    avatar = models.URLField()

    def __str__(self):
        return self.name


class Board(models.Model):
    title = models.CharField(max_length=100)

    def __str__(self):
        return self.title


class TaskLane(models.Model):
    title = models.CharField(max_length=100)
    board_id = models.ForeignKey('Board', models.CASCADE)
    order = models.IntegerField()

    def __str__(self):
        return self.title


class Task(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    tags = models.CharField(max_length=100, blank=True)
    due_by = models.DateTimeField()
    board_id = models.ForeignKey('Board', models.CASCADE)
    lane_id = models.ForeignKey('TaskLane', models.CASCADE)
    order = models.IntegerField()
    assigned_to = models.ForeignKey('User', models.CASCADE)

    def __str__(self):
        return self.title
