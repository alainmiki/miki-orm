#!/usr/bin/env python3
"""
Example 6: School Management System
======================================
Demonstrates:
  - Full migration workflow (makemigrations + migrate)
  - Diverse field types: DecimalField, DateField, IntegerField, BooleanField,
    CharField, TextField, ForeignKey, JSONField, UUIDField
  - Advanced queries: filtering, ordering, get_or_create, update_or_create,
    bulk_create, values/values_list, delete
  - Custom Meta ordering and table_name
  - Proper DB connection handling via MigrationEngine
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mikiorm
from mikiorm import makemigrations, migrate, models, register

DB_PATH = os.path.join(os.path.dirname(__file__), "school.db")


def cleanup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


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

@register
class Student(models.Model):
    """A student enrolled in the school."""
    admission_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField(null=True)
    email = models.EmailField(null=True)
    phone = models.CharField(max_length=20, null=True)
    gpa = models.DecimalField(max_digits=4, decimal_places=2, default="0.00")
    is_active = models.BooleanField(default=True)
    enrollment_date = models.DateField(auto_now_add=True)
    profile_data = models.JSONField(null=True)  # e.g. {"emergency_contact": "..."}

    class Meta:
        table_name = "students"
        ordering = ["last_name", "first_name"]

    def __repr__(self):
        return f"<Student {self.admission_number}: {self.first_name} {self.last_name}>"


@register
class Teacher(models.Model):
    """A teacher at the school."""
    employee_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField()
    department = models.CharField(max_length=100, null=True)
    hire_date = models.DateField(auto_now_add=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default="0.00")
    is_active = models.BooleanField(default=True)
    bio = models.TextField(null=True)

    class Meta:
        table_name = "teachers"

    def __repr__(self):
        return f"<Teacher {self.employee_id}: {self.first_name} {self.last_name}>"


@register
class Course(models.Model):
    """An academic course taught by a teacher."""
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(null=True)
    teacher = models.ForeignKey(to="Teacher", on_delete=models.SET_NULL, null=True)
    credits = models.PositiveIntegerField(default=3)
    max_enrollment = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    schedule = models.JSONField(null=True)  # e.g. {"days": ["Mon", "Wed"], "time": "10:00-11:30"}

    class Meta:
        table_name = "courses"
        ordering = ["code"]

    def __repr__(self):
        return f"<Course {self.code}: {self.name}>"


@register
class Enrollment(models.Model):
    """Student enrollment in a course with grade tracking."""
    student = models.ForeignKey(to="Student", on_delete=models.CASCADE)
    course = models.ForeignKey(to="Course", on_delete=models.CASCADE)
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    semester = models.CharField(max_length=20, default="Fall 2026")
    is_completed = models.BooleanField(default=False)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "enrollments"


@register
class Attendance(models.Model):
    """Daily attendance record for a student in a course."""
    student = models.ForeignKey(to="Student", on_delete=models.CASCADE)
    course = models.ForeignKey(to="Course", on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=10, default="present")  # present, absent, late
    notes = models.CharField(max_length=200, null=True)

    class Meta:
        table_name = "attendance"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run():
    cleanup()
    configure()

    # =========================================================================
    # PART 1: Migration Workflow
    # =========================================================================
    print("=" * 60)
    print("PART 1: Migrations")
    print("=" * 60)

    # Generate and apply all table-creation migrations through the standard flow
    makemigrations()
    migrate()
    print("  [OK] Database schema initialized via migrations.")

    # =========================================================================
    # PART 2: Create Data
    # =========================================================================
    print("\n" + "=" * 60)
    print("PART 2: Create Records")
    print("=" * 60)

    # Create teachers
    t1 = Teacher.objects.create(
        employee_id="T001", first_name="Dr. Smith", last_name="Johnson",
        email="smith@school.edu", department="Mathematics",
        salary="75000.00", bio="PhD in Applied Mathematics",
    )
    t2 = Teacher.objects.create(
        employee_id="T002", first_name="Dr. Emily", last_name="Chen",
        email="chen@school.edu", department="Physics",
        salary="80000.00", bio="PhD in Quantum Physics",
    )
    t3 = Teacher.objects.create(
        employee_id="T003", first_name="Prof. Robert", last_name="Williams",
        email="williams@school.edu", department="Computer Science",
        salary="85000.00", bio="PhD in Computer Science",
    )
    print(f"Teachers: {Teacher.objects.count()}")

    # Create students
    students_data = [
        {"admission_number": "S001", "first_name": "Alice", "last_name": "Anderson",
         "email": "alice@school.edu", "gpa": "3.85",
         "profile_data": {"major": "Computer Science", "year": 2}},
        {"admission_number": "S002", "first_name": "Bob", "last_name": "Brown",
         "email": "bob@school.edu", "gpa": "3.50",
         "profile_data": {"major": "Physics", "year": 3}},
        {"admission_number": "S003", "first_name": "Carol", "last_name": "Clark",
         "email": "carol@school.edu", "gpa": "3.92",
         "profile_data": {"major": "Mathematics", "year": 1}},
        {"admission_number": "S004", "first_name": "David", "last_name": "Davis",
         "email": "david@school.edu", "gpa": "2.75",
         "profile_data": {"major": "Computer Science", "year": 2}},
        {"admission_number": "S005", "first_name": "Emma", "last_name": "Evans",
         "email": "emma@school.edu", "gpa": "3.60",
         "profile_data": {"major": "Mathematics", "year": 3}},
        {"admission_number": "S006", "first_name": "Frank", "last_name": "Foster",
         "email": "frank@school.edu", "gpa": "3.10",
         "profile_data": {"major": "Physics", "year": 1}},
    ]
    Student.objects.bulk_create([Student(**s) for s in students_data])
    print(f"Students: {Student.objects.count()}")

    # Create courses
    c1 = Course.objects.create(
        code="CS101", name="Introduction to Computer Science",
        teacher=t3, credits=4,
        schedule={"days": ["Mon", "Wed", "Fri"], "time": "09:00-10:00"},
    )
    c2 = Course.objects.create(
        code="MATH201", name="Calculus III",
        teacher=t1, credits=4,
        schedule={"days": ["Tue", "Thu"], "time": "10:00-11:30"},
    )
    c3 = Course.objects.create(
        code="PHYS301", name="Quantum Mechanics",
        teacher=t2, credits=3,
        schedule={"days": ["Mon", "Wed"], "time": "14:00-15:30"},
    )
    c4 = Course.objects.create(
        code="CS301", name="Algorithms",
        teacher=t3, credits=3, max_enrollment=20,
        schedule={"days": ["Tue", "Thu"], "time": "13:00-14:30"},
    )
    print(f"Courses: {Course.objects.count()}")

    # =========================================================================
    # PART 3: Enrollments and Advanced Queries
    # =========================================================================
    print("\n" + "=" * 60)
    print("PART 3: Enrollments & Advanced Queries")
    print("=" * 60)

    # Create enrollments
    enrollments = [
        Enrollment(student=Student.objects.get(admission_number="S001"), course=c1, grade="3.50", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S001"), course=c2, grade="4.00", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S002"), course=c2, grade="3.75", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S002"), course=c3, grade="3.25", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S003"), course=c1, grade="4.00", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S003"), course=c2, grade="3.90", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S003"), course=c3, grade="3.80", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S004"), course=c1, grade="2.50", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S004"), course=c4, grade=None, semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S005"), course=c2, grade="3.40", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S005"), course=c3, grade="3.60", semester="Fall 2026"),
        Enrollment(student=Student.objects.get(admission_number="S006"), course=c2, grade=None, semester="Fall 2026"),
    ]
    Enrollment.objects.bulk_create(enrollments)
    print(f"Enrollments: {Enrollment.objects.count()}")

    # Create attendance records
    from datetime import date
    Attendance.objects.create(student=Student.objects.get(admission_number="S001"), course=c1, date=date(2026, 9, 1), status="present")
    Attendance.objects.create(student=Student.objects.get(admission_number="S002"), course=c1, date=date(2026, 9, 1), status="absent")
    Attendance.objects.create(student=Student.objects.get(admission_number="S003"), course=c1, date=date(2026, 9, 1), status="present")
    Attendance.objects.create(student=Student.objects.get(admission_number="S004"), course=c1, date=date(2026, 9, 1), status="late")
    Attendance.objects.create(student=Student.objects.get(admission_number="S001"), course=c2, date=date(2026, 9, 1), status="present")
    print(f"Attendance records: {Attendance.objects.count()}")

    # =========================================================================
    # PART 4: Complex Queries
    # =========================================================================
    print("\n" + "=" * 60)
    print("PART 4: Complex Queries")
    print("=" * 60)

    # Get all students in CS101
    cs101_students = Student.objects.filter(enrollment__course=c1)
    print(f"\nStudents in CS101: {[f'{s.first_name} {s.last_name}' for s in cs101_students]}")

    # Get all courses with GPA > 3.5 students
    high_gpa_enrollments = Enrollment.objects.filter(grade__gte=3.5)
    print(f"\nHigh GPA enrollments (>= 3.5): {high_gpa_enrollments.count()}")
    for e in high_gpa_enrollments:
        print(f"  {e.student.first_name} {e.student.last_name} - {e.course.code}: {e.grade}")

    # Get students ordered by GPA descending
    top_students = Student.objects.all().order_by("-gpa")
    print(f"\nStudents ranked by GPA:")
    for i, s in enumerate(top_students, 1):
        print(f"  {i}. {s.first_name} {s.last_name} — GPA: {s.gpa}")

    # Get active students with GPA >= 3.5
    honors = Student.objects.filter(is_active=True, gpa__gte="3.50")
    print(f"\nHonors students (active, GPA >= 3.50): {honors.count()}")

    # Get courses taught by a specific department
    cs_courses = Course.objects.filter(teacher__department="Computer Science")
    print(f"\nComputer Science courses: {[c.name for c in cs_courses]}")

    # Get teachers with salary > 75000
    well_paid = Teacher.objects.filter(salary__gte=80000)
    print(f"\nWell-paid teachers (salary >= $80,000): {[f'{t.first_name} {t.last_name}' for t in well_paid]}")

    # Courses with no grade yet (in-progress)
    in_progress = Enrollment.objects.filter(grade__isnull=True)
    print(f"\nIn-progress enrollments (no grade): {in_progress.count()}")
    for e in in_progress:
        print(f"  {e.student.first_name} {e.student.last_name} in {e.course.code}")

    # Get courses sorted by number of enrollments
    print(f"\nCourses by enrollment count:")
    for course in Course.objects.all():
        count = Enrollment.objects.filter(course=course).count()
        print(f"  {course.code}: {count} students enrolled")

    # Get all enrollments for a student using values()
    alice_enrollments = Enrollment.objects.filter(student__admission_number="S001").values("course__code", "grade", "semester")
    print(f"\nAlice's enrollments (values): {alice_enrollments}")

    # Get student names as tuples
    student_names = Student.objects.values_list("first_name", "last_name")
    print(f"\nStudent names (as tuples): {student_names}")

    # =========================================================================
    # PART 5: Update, Delete, and Exception Handling
    # =========================================================================
    print("\n" + "=" * 60)
    print("PART 5: Updates, Deletes, and Exceptions")
    print("=" * 60)

    # Update: Give all CS students a GPA boost
    updated = Student.objects.filter(profile_data__major="Computer Science").update(gpa="3.90")
    print(f"\nUpdated GPA for {updated} CS students")

    # get_or_create: Enroll a student
    student, created = Enrollment.objects.get_or_create(
        student__admission_number="S006",
        course=c1,
        defaults={"grade": "3.00", "semester": "Fall 2026"},
    )
    print(f"get_or_create enrollment: created={created}")

    # update_or_create: Update or create teacher
    teacher, created = Teacher.objects.update_or_create(
        employee_id="T004",
        defaults={"first_name": "Grace", "last_name": "Hopper",
                  "email": "grace@school.edu", "department": "CS",
                  "salary": "90000.00"},
    )
    print(f"update_or_create teacher: created={created}, name={teacher.first_name} {teacher.last_name}")

    # Mark a student as inactive (soft delete)
    Student.objects.filter(admission_number="S006").update(is_active=False)
    active_count = Student.objects.filter(is_active=True).count()
    print(f"\nAfter deactivating S006: {active_count} active students")

    # Delete a course (cascades to enrollments and attendance)
    course_to_delete = Course.objects.get(code="CS301")
    course_to_delete.delete()
    print(f"Deleted CS301 — remaining courses: {Course.objects.count()}")
    print(f"Remaining enrollments: {Enrollment.objects.count()}")

    # Exception handling
    try:
        Student.objects.get(admission_number="S999")
    except models.ObjectDoesNotExist:
        print("\nObjectDoesNotExist correctly raised for missing student")

    # =========================================================================
    # PART 6: Instance-level Operations
    # =========================================================================
    print("\n" + "=" * 60)
    print("PART 6: Instance Operations")
    print("=" * 60)

    # Modify and save a student
    bob = Student.objects.get(admission_number="S002")
    print(f"\nBefore: {bob.first_name} GPA={bob.gpa}")
    bob.gpa = "3.80"
    bob.save()
    bob_refreshed = Student.objects.get(admission_number="S002")
    print(f"After save: {bob_refreshed.first_name} GPA={bob_refreshed.gpa}")

    # Delete instance
    bob.delete()
    print(f"Deleted Bob — remaining students: {Student.objects.count()}")

    # to_dict()
    carol = Student.objects.get(admission_number="S003")
    print(f"\nCarol as dict: {carol.to_dict()}")

    # Teacher to_dict
    teacher = Teacher.objects.first()
    print(f"\nFirst teacher as dict: {teacher.to_dict()}")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Students:     {Student.objects.count()}")
    print(f"Teachers:     {Teacher.objects.count()}")
    print(f"Courses:      {Course.objects.count()}")
    print(f"Enrollments:  {Enrollment.objects.count()}")
    print(f"Attendance:   {Attendance.objects.count()}")

    print("\n✅ Example 6 — School management system completed successfully!")


if __name__ == "__main__":
    run()