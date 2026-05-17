#!/usr/bin/env python3
"""
Example 4: Task Management System
===================================
Demonstrates:
  - DateTimeField with auto_now and auto_now_add
  - BooleanField for status tracking
  - Choice fields (via CharField + manual choices)
  - PositiveIntegerField for priority levels
  - Complex filtering: date ranges, boolean flags, multi-condition queries
  - Ordering by multiple fields
  - first(), last(), count(), exists() patterns
  - Batch update operations
  - Custom manager with domain-specific query methods
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mikiorm
from mikiorm import makemigrations, migrate, models
from mikiorm.managers.base import Manager

DB_PATH = os.path.join(os.path.dirname(__file__), "tasks.db")


def cleanup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    import shutil
    mig_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
    if os.path.exists(mig_dir):
        shutil.rmtree(mig_dir)


def configure():
    mikiorm.configure({
        "default": {
            "ENGINE": "sqlite",
            "NAME": DB_PATH,
        }
    })


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

class Project(models.Model):
    """A project containing tasks."""
    name = models.CharField(max_length=150)
    slug = models.SlugField()
    description = models.TextField(null=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "projects"


class TaskManager(Manager):
    """Custom manager with domain-specific queries."""

    def active(self):
        """Return only non-completed, non-archived tasks."""
        return self.filter(is_completed=False)

    def overdue(self):
        """Return tasks past their due date that aren't completed."""
        now = datetime.now()
        return self.filter(due_date__lt=now, is_completed=False)

    def for_project(self, project):
        """Return tasks for a given project."""
        return self.filter(project=project)


class Task(models.Model):
    """A task within a project."""
    PRIORITY_CHOICES = (
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    )

    STATUS_CHOICES = (
        ("todo", "To Do"),
        ("in_progress", "In Progress"),
        ("review", "In Review"),
        ("done", "Done"),
    )

    title = models.CharField(max_length=200)
    description = models.TextField(null=True)
    project = models.ForeignKey(to="Project", on_delete=models.CASCADE)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="todo")
    assignee = models.CharField(max_length=100, null=True)
    due_date = models.DateTimeField(null=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True)
    estimated_hours = models.PositiveIntegerField(default=0)
    actual_hours = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Use custom manager
    objects = TaskManager(model=None)  # Will be properly set by metaclass

    class Meta:
        table_name = "tasks"
        ordering = ["-created_at"]

    def mark_complete(self):
        """Mark task as complete and record completion time."""
        self.is_completed = True
        self.completed_at = datetime.now()
        self.status = "done"
        self.save()

    def __repr__(self):
        return f"<Task '{self.title}' [{self.priority}]>"


class TimeLog(models.Model):
    """Track time spent working on a task."""
    task = models.ForeignKey(to="Task", on_delete=models.CASCADE)
    hours = models.PositiveIntegerField()
    description = models.CharField(max_length=200, null=True)
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "time_logs"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run():
    cleanup()
    configure()

    # Run migrations so tables are created through the migration workflow
    makemigrations([Project, Task, TimeLog])
    migrate()
    print("  [OK] Schema initialized via migrations.")

    # ---- Create projects ----
    proj1 = Project.objects.create(
        name="Website Redesign", slug="website-redesign",
        description="Redesign the company website",
    )
    proj2 = Project.objects.create(
        name="API Migration", slug="api-migration",
        description="Migrate REST API to v2",
    )
    proj3 = Project.objects.create(
        name="Mobile App", slug="mobile-app",
        description="Build the iOS/Android app",
        is_archived=True,
    )
    print(f"Projects: {Project.objects.count()}")

    # ---- Create tasks with various priorities and statuses ----
    now = datetime.now()

    tasks_data = [
        {"title": "Design homepage mockup", "project": proj1, "priority": "high",
         "status": "in_progress", "assignee": "Alice", "due_date": now + timedelta(days=3),
         "estimated_hours": 8},
        {"title": "Implement user auth", "project": proj1, "priority": "critical",
         "status": "in_progress", "assignee": "Bob", "due_date": now + timedelta(days=5),
         "estimated_hours": 16},
        {"title": "Write API docs", "project": proj2, "priority": "low",
         "status": "todo", "assignee": "Charlie", "due_date": now + timedelta(days=10),
         "estimated_hours": 4},
        {"title": "Database schema review", "project": proj2, "priority": "high",
         "status": "review", "assignee": "Alice", "due_date": now - timedelta(days=1),
         "estimated_hours": 6},
        {"title": "Fix navbar responsive bug", "project": proj1, "priority": "medium",
         "status": "todo", "due_date": now + timedelta(days=2),
         "estimated_hours": 3},
        {"title": "Set up CI/CD pipeline", "project": proj2, "priority": "high",
         "status": "done", "assignee": "Bob", "is_completed": True,
         "completed_at": now - timedelta(days=2),
         "estimated_hours": 4, "actual_hours": 5},
        {"title": "Write unit tests", "project": proj1, "priority": "high",
         "status": "todo", "assignee": "Charlie", "due_date": now + timedelta(days=7),
         "estimated_hours": 12},
        {"title": "Design icon set", "project": proj3, "priority": "low",
         "status": "done", "is_completed": True,
         "completed_at": now - timedelta(days=20),
         "estimated_hours": 10, "actual_hours": 8},
    ]

    for data in tasks_data:
        Task.objects.create(**data)

    print(f"Tasks: {Task.objects.count()}")

    # ---- Create time logs ----
    for task in Task.objects.filter(is_completed=True):
        TimeLog.objects.create(task=task, hours=task.actual_hours,
                               description=f"Completed {task.title}")
    print(f"Time logs: {TimeLog.objects.count()}")

    # ---- FILTERING DEMOS ----

    # Active tasks (using custom manager)
    active = Task.objects.active()
    print(f"\nActive tasks: {active.count()}")
    for t in active:
        print(f"  [{t.priority}] {t.title} — {t.status}")

    # Tasks assigned to Alice
    alice_tasks = Task.objects.filter(assignee="Alice")
    print(f"\nAlice's tasks: {alice_tasks.count()}")

    # High-priority tasks
    high_priority = Task.objects.filter(priority="high")
    print(f"\nHigh priority tasks: {high_priority.count()}")

    # Tasks due within 7 days
    week_ahead = now + timedelta(days=7)
    due_soon = Task.objects.filter(due_date__lt=week_ahead, is_completed=False)
    print(f"\nTasks due within 7 days: {due_soon.count()}")
    for t in due_soon.order_by("due_date"):
        days_left = (t.due_date - now).days
        print(f"  '{t.title}' — due in {days_left} days [{t.priority}]")

    # Overdue tasks (using custom manager)
    overdue = Task.objects.overdue()
    print(f"\nOverdue tasks: {overdue.count()}")
    for t in overdue:
        print(f"  '{t.title}' — was due on {t.due_date}")

    # tasks in project 1 that are NOT done
    proj1_active = Task.objects.filter(project=proj1).exclude(status="done")
    print(f"\nProject 1 active tasks: {proj1_active.count()}")

    # ---- ORDERING ----
    by_priority = Task.objects.all().order_by("priority", "-created_at")
    print("\nTasks by priority:")
    for t in by_priority:
        print(f"  {t.priority}: {t.title}")

    # ---- first() / last() ----
    first_task = Task.objects.all().first()
    last_task = Task.objects.all().last()
    print(f"\nFirst task: {first_task.title}")
    print(f"Last task:  {last_task.title}")

    # ---- COUNT ----
    print(f"\nTotal tasks: {Task.objects.count()}")
    print(f"Completed tasks: {Task.objects.filter(is_completed=True).count()}")
    print(f"Tasks for proj1: {Task.objects.filter(project=proj1).count()}")

    # ---- EXISTS ----
    print(f"\nAny overdue tasks? {Task.objects.overdue().exists()}")
    print(f"Any tasks for non-existent project? "
          f"{Task.objects.filter(project__id=999).exists()}")

    # ---- VALUES / VALUES_LIST ----
    task_summaries = Task.objects.filter(is_completed=False).values("title", "priority", "assignee")
    print("\nActive task summaries:")
    for s in task_summaries:
        print(f"  {s}")

    priorities = Task.objects.values_list("priority", flat=False)
    print(f"\nAll task priorities (as tuples): {priorities}")

    # ---- BATCH UPDATE via QuerySet ----
    updated = Task.objects.filter(priority="low").update(status="done")
    print(f"\nAuto-completed {updated} low-priority tasks")

    # ---- COMPLETE a task via instance method ----
    task_to_complete = Task.objects.filter(is_completed=False).first()
    if task_to_complete:
        task_to_complete.mark_complete()
        print(f"Completed task: '{task_to_complete.title}' at {task_to_complete.completed_at}")

    # ---- get() with exception handling ----
    try:
        Task.objects.get(title="Nonexistent Task")
    except models.ObjectDoesNotExist:
        print("\nObjectDoesNotExist correctly raised")

    # ---- get_or_create / update_or_create ----
    task, was_new = Task.objects.get_or_create(
        title="Essential Bug Fix",
        defaults={
            "project": proj2, "priority": "critical",
            "status": "todo", "due_date": now,
        },
    )
    print(f"\nget_or_create: new={was_new}, id={task.id}")

    task, was_new = Task.objects.update_or_create(
        title="Essential Bug Fix",
        defaults={"priority": "high", "status": "in_progress"},
    )
    print(f"update_or_create: new={was_new}, priority={task.priority}, status={task.status}")

    # ---- TimeLog queries (reverse FK lookup) ----
    bob_logs = TimeLog.objects.filter(task__assignee="Bob")
    print(f"\nTime logs for Bob's tasks: {bob_logs.count()}")

    # ---- DELETION ----
    archived_project = Project.objects.filter(is_archived=True).first()
    if archived_project:
        archived_project.delete()
        print(f"\nDeleted archived project — remaining projects: {Project.objects.count()}")

    # ---- to_dict ----
    print(f"\nTask as dict: {Task.objects.first().to_dict()}")

    print("\n✅ Example 4 — Task management completed successfully!")


if __name__ == "__main__":
    run()