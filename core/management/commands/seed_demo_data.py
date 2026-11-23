from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    AuditLog, ClassSchedule, CurriculumSubject, Department, Enrollment,
    EnrollmentSubject, Fee, Grade, Instructor, Payment, Program, Room,
    SchoolTerm, Section, Student, StudentDocument, Subject, SubjectOffering,
)
from core.services import DOCUMENT_REQUIREMENTS, recalculate_assessment, save_initial_subjects


class Command(BaseCommand):
    help = (
        "Create or complete a fictional, idempotent enrollment demonstration dataset. "
        "Only records with DEMO identifiers/usernames are managed by this command."
    )

    ROLE_DETAILS = {
        "Administrator": ("Demo", "Administrator", "demo_administrator@example.invalid"),
        "Registrar": ("Riley", "Registrar", "demo_registrar@example.invalid"),
        "Cashier": ("Casey", "Cashier", "demo_cashier@example.invalid"),
        "Instructor": ("Jordan", "Instructor", "demo_instructor@example.invalid"),
        "Student": ("Alex", "Demo Student", "demo_student@example.invalid"),
    }
    INITIAL_PASSWORD = "DemoPass!2026"

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        User = get_user_model()
        users = {}

        # Reset only the explicitly named demo accounts to their documented
        # password so a local demonstration can be recovered at any time.
        for role, (first_name, last_name, email) in self.ROLE_DETAILS.items():
            group, _ = Group.objects.get_or_create(name=role)
            username = f"demo_{role.lower()}"
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name, "email": email},
            )
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.set_password(self.INITIAL_PASSWORD)
            if role == "Administrator":
                user.is_staff = True
            user.save()
            user.groups.add(group)
            users[role] = user

        college, _ = Department.objects.update_or_create(
            code="DEMO-CST",
            defaults={"name": "Demo College of Science and Technology"},
        )
        program, _ = Program.objects.update_or_create(
            code="DEMO-BSCS",
            defaults={
                "name": "Bachelor of Science in Computer Science (Demo)",
                "department": college,
                "years_to_complete": 4,
            },
        )
        # Supporting options keep every relational dropdown useful in a fresh
        # demo database (at least three valid records for each FK selector).
        college_2, _ = Department.objects.update_or_create(
            code="DEMO-CBA", defaults={"name": "Demo College of Business and Accountancy"}
        )
        college_3, _ = Department.objects.update_or_create(
            code="DEMO-CTE", defaults={"name": "Demo College of Teacher Education"}
        )
        program_2, _ = Program.objects.update_or_create(
            code="DEMO-BSA", defaults={"name": "Bachelor of Science in Accountancy (Demo)", "department": college_2, "years_to_complete": 4}
        )
        program_3, _ = Program.objects.update_or_create(
            code="DEMO-BSED", defaults={"name": "Bachelor of Secondary Education (Demo)", "department": college_3, "years_to_complete": 4}
        )

        term, _ = SchoolTerm.objects.update_or_create(
            name="1st Semester",
            school_year="2026-2027",
            defaults={
                "is_open": True,
                "starts_on": date(2026, 8, 1),
                "ends_on": date(2026, 12, 20),
                "enrollment_opens": now - timedelta(days=1),
                "enrollment_closes": now + timedelta(days=60),
                "add_drop_opens": now - timedelta(days=1),
                "add_drop_closes": now + timedelta(days=30),
                "passing_grade": Decimal("3.00"),
                "minimum_units": Decimal("0.0"),
                "maximum_units": Decimal("30.0"),
            },
        )
        prior_term, _ = SchoolTerm.objects.update_or_create(
            name="1st Semester",
            school_year="2025-2026",
            defaults={
                "is_open": False,
                "starts_on": date(2025, 8, 1),
                "ends_on": date(2025, 12, 20),
                "enrollment_opens": None,
                "enrollment_closes": None,
                "add_drop_opens": None,
                "add_drop_closes": None,
                "passing_grade": Decimal("3.00"),
                "minimum_units": Decimal("0.0"),
                "maximum_units": Decimal("30.0"),
            },
        )
        second_term, _ = SchoolTerm.objects.update_or_create(
            name="2nd Semester", school_year="2026-2027",
            defaults={
                "is_open": False, "starts_on": date(2027, 1, 5), "ends_on": date(2027, 5, 30),
                "enrollment_opens": None, "enrollment_closes": None,
                "add_drop_opens": None, "add_drop_closes": None,
                "passing_grade": Decimal("3.00"), "minimum_units": Decimal("0.0"),
                "maximum_units": Decimal("30.0"),
            },
        )

        subject_data = [
            ("DEMO-CS101", "Introduction to Computing", Decimal("3.0"),
             "Foundational concepts in computer systems, information technology, and computational thinking."),
            ("DEMO-CS102", "Programming Fundamentals", Decimal("3.0"),
             "Introduction to programming logic, algorithms, variables, control structures, and problem solving."),
            ("DEMO-CS201", "Data Structures", Decimal("3.0"),
             "Fundamental data structures, algorithm analysis, and their applications in software development."),
        ]
        subjects = {}
        for code, title, units, description in subject_data:
            subjects[code], _ = Subject.objects.update_or_create(
                code=code,
                defaults={"title": title, "units": units, "description": description},
            )

        curricula = {}
        for code, year in [("DEMO-CS101", 1), ("DEMO-CS102", 1), ("DEMO-CS201", 2)]:
            curricula[code], _ = CurriculumSubject.objects.get_or_create(
                program=program, subject=subjects[code], year_level=year, semester=term.name,
            )
        curricula["DEMO-CS102"].prerequisites.set([subjects["DEMO-CS101"]])
        curricula["DEMO-CS201"].prerequisites.set([subjects["DEMO-CS102"]])

        instructor, _ = Instructor.objects.update_or_create(
            user=users["Instructor"],
            defaults={"employee_no": "DEMO-EMP-001", "department": college},
        )
        room, _ = Room.objects.update_or_create(
            code="DEMO-ROOM-101", defaults={"capacity": 40},
        )
        room_2, _ = Room.objects.update_or_create(code="DEMO-ROOM-102", defaults={"capacity": 35})
        room_3, _ = Room.objects.update_or_create(code="DEMO-LAB-201", defaults={"capacity": 30})
        instructor_records = [instructor]
        for number, (first, last, dept) in enumerate([
            ("Taylor", "Demo Instructor Two", college_2),
            ("Morgan", "Demo Instructor Three", college_3),
        ], start=2):
            username = f"demo_instructor_{number}"
            instructor_user, _ = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": f"{username}@example.invalid"},
            )
            instructor_user.first_name = first
            instructor_user.last_name = last
            instructor_user.email = f"{username}@example.invalid"
            instructor_user.set_password(self.INITIAL_PASSWORD)
            instructor_user.save()
            instructor_user.groups.add(Group.objects.get(name="Instructor"))
            extra_instructor, _ = Instructor.objects.update_or_create(
                user=instructor_user,
                defaults={"employee_no": f"DEMO-EMP-00{number}", "department": dept},
            )
            instructor_records.append(extra_instructor)

        offerings = {}
        subject_offerings = {}
        for code, year in [("DEMO-CS101", 1), ("DEMO-CS102", 1), ("DEMO-CS201", 2)]:
            subject_offerings[code] = []
            for section_letter in ("A", "B", "C"):
                section, _ = Section.objects.update_or_create(
                    code=f"DEMO-{year}{section_letter}", term=term,
                    defaults={"program": program, "year_level": year},
                )
                instructor_for_section = instructor_records[("A", "B", "C").index(section_letter)]
                offering, _ = SubjectOffering.objects.update_or_create(
                    curriculum_subject=curricula[code], section=section,
                    defaults={"instructor": instructor_for_section, "capacity": 40},
                )
                subject_offerings[code].append(offering)
            offerings[code] = subject_offerings[code][0]

        # Give all three section options per subject a real schedule. Unique
        # day/time combinations and matching room/instructor assignments avoid
        # creating demo timetable conflicts.
        slot_starts = [(time(8, 0), time(9, 30)), (time(10, 0), time(11, 30))]
        room_records = [room, room_2, room_3]
        schedule_index = 0
        for subject_index, code in enumerate(("DEMO-CS101", "DEMO-CS102", "DEMO-CS201")):
            for section_index, offering in enumerate(subject_offerings[code]):
                day = str(schedule_index % 7)
                slot = min(schedule_index // 7, len(slot_starts) - 1)
                start, end = slot_starts[slot]
                assigned_room = room_records[section_index]
                schedule, created = ClassSchedule.objects.get_or_create(
                    offering=offering, day=day, start_time=start, end_time=end,
                    defaults={"room": assigned_room},
                )
                if not created and schedule.room_id != assigned_room.pk:
                    schedule.room = assigned_room
                    schedule.save(update_fields=["room"])
                schedule_index += 1

        Fee.objects.update_or_create(
            name="Demo Tuition per Unit",
            defaults={"amount": Decimal("500.00"), "is_per_unit": True, "active": True},
        )
        Fee.objects.update_or_create(
            name="Demo Miscellaneous Fee",
            defaults={"amount": Decimal("1500.00"), "is_per_unit": False, "active": True},
        )
        Fee.objects.update_or_create(
            name="Demo Laboratory Fee",
            defaults={"amount": Decimal("350.00"), "is_per_unit": False, "active": True},
        )

        student_user = users["Student"]
        student, _ = Student.objects.update_or_create(
            user=student_user,
            defaults={
                "first_name": "Alex",
                "middle_name": "Sample",
                "last_name": "Demo Student",
                "birth_date": date(2005, 5, 14),
                "gender": "X",
                "email": student_user.email,
                "phone": "09170000001",
                "address": "Demo Street, Puerto Princesa City, Palawan",
                "program": program,
                "year_level": 2,
                "admission_category": "REGULAR",
                "enrollment_standing": "IRREGULAR",
                "account_status": "ACTIVE",
                "must_change_password": True,
            },
        )

        # Historical passing grade: CS101 is complete, while CS102 is not.
        # The current proposed enrollment should therefore add CS102 instead
        # of allowing the student to take dependent subject CS201.
        history_section, _ = Section.objects.update_or_create(
            code="DEMO-HIST-1A", term=prior_term,
            defaults={"program": program, "year_level": 1},
        )
        history_offering, _ = SubjectOffering.objects.update_or_create(
            curriculum_subject=curricula["DEMO-CS101"], section=history_section,
            defaults={"instructor": instructor, "capacity": 40},
        )
        history_enrollment, _ = Enrollment.objects.get_or_create(
            student=student, term=prior_term,
            defaults={"enrollment_type": "REGULAR", "status": "ENROLLED", "approved_by": users["Registrar"]},
        )
        history_item, _ = EnrollmentSubject.objects.get_or_create(
            enrollment=history_enrollment, offering=history_offering,
        )
        Grade.objects.update_or_create(
            enrollment_subject=history_item,
            defaults={
                "prelim": Decimal("2.50"),
                "midterm": Decimal("2.25"),
                "final": Decimal("2.00"),
                "remarks": "Passed - demo academic history",
            },
        )

        # Create the current enrollment once. Preserve any student edits if the
        # command is rerun after the student has customized their draft.
        enrollment, enrollment_created = Enrollment.objects.get_or_create(
            student=student, term=term,
            defaults={"enrollment_type": "IRREGULAR", "status": "PENDING"},
        )
        if enrollment_created:
            save_initial_subjects(enrollment, users["Registrar"])
        recalculate_assessment(enrollment)

        # Two additional fictional student/enrollment records ensure the
        # student, enrollment, and enrolled-subject FK dropdowns each offer
        # at least three valid selections on a clean seeded installation.
        support_students = []
        for number, (first, last, selected_program, selected_term) in enumerate([
            ("Jamie", "Sample Two", program, term),
            ("Casey", "Sample Three", program, term),
        ], start=2):
            support_student, _ = Student.objects.update_or_create(
                student_id=f"DEMO-STU-00000{number}",
                defaults={
                    "first_name": first, "middle_name": "Demo", "last_name": last,
                    "birth_date": date(2004 + number, 3, 12), "gender": ["F", "M"][number - 2],
                    "email": f"demo_student_{number}@example.invalid", "phone": f"0917000000{number}",
                    "address": "Demo Campus Area, Puerto Princesa City, Palawan",
                    "program": selected_program, "year_level": 1,
                    "admission_category": "FRESHMAN" if number == 2 else "TRANSFEREE",
                    "enrollment_standing": "REGULAR", "account_status": "ACTIVE",
                    "must_change_password": False,
                },
            )
            support_students.append((support_student, selected_term))

        for support_student, support_term in support_students:
            support_enrollment, _ = Enrollment.objects.get_or_create(
                student=support_student, term=support_term,
                defaults={"enrollment_type": "REGULAR", "status": "PENDING"},
            )
            if not support_enrollment.subjects.exists():
                selected_offering = offerings["DEMO-CS101"]
                EnrollmentSubject.objects.get_or_create(
                    enrollment=support_enrollment, offering=selected_offering,
                )
            recalculate_assessment(support_enrollment)

        Payment.objects.get_or_create(
            enrollment=enrollment,
            reference_no="DEMO-GCASH-2026-0001",
            defaults={
                "amount": Decimal("500.00"),
                "method": "GCASH",
                "verification_status": "PENDING",
                "recorded_by": users["Cashier"],
            },
        )

        for document_name in DOCUMENT_REQUIREMENTS.get(enrollment.enrollment_type, []):
            StudentDocument.objects.get_or_create(
                student=student, term=term, document_type=document_name,
                defaults={
                    "status": "PENDING",
                    "notes": "Demo checklist item. Upload the supporting document for review.",
                },
            )

        AuditLog.objects.get_or_create(
            user=users["Registrar"],
            action="Seeded demonstration enrollment data",
            object_type="Enrollment",
            object_id=str(enrollment.pk),
        )

        self.stdout.write(self.style.SUCCESS(
            "Demo data is ready. All demo accounts use username demo_<role> "
            "and initial password DemoPass!2026. The demo student must change "
            "the password on first login. The sample GCash payment remains "
            "PENDING until verified by the cashier."
        ))
