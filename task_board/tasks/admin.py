from django.contrib import admin
from .models import *


@admin.register(User)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'avatar']


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ['id', 'title']


@admin.register(TaskLane)
class TaskLaneAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'order', 'board_id']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'description',
                    'due_by', 'order', 'assigned_to', 'lane_id', 'board_id']
