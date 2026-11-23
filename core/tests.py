from decimal import Decimal
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import Group
from django.test import TestCase
from django import forms
from django.urls import reverse
from django.core.management import call_command
from .models import Department, Program, Student, SchoolTerm, Subject, CurriculumSubject, Instructor, Room, Section, SubjectOffering, Enrollment, EnrollmentSubject, Fee, ClassSchedule, AssessmentItem, Payment, StudentDocument, Grade, AdmissionApplication, AcademicRecord, FinancialAdjustment, EnrollmentChange
from .forms import StudentForm, EnrollmentForm, PaymentForm, StudentDocumentUploadForm
from .views import MANAGED_MODELS
from .services import generate_initial_subjects, validate_enrollment, ensure_cor_for_enrolled, issue_cor
from .views import create_student_portal_account

class EnrollmentWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model(); cls.admin=User.objects.create_user(username="registrar",password="StrongPass!123")
        cls.student_user=User.objects.create_user(username="student",password="StrongPass!123")
        registrar,_=Group.objects.get_or_create(name="Registrar"); student_group,_=Group.objects.get_or_create(name="Student")
        cls.admin.groups.add(registrar); cls.student_user.groups.add(student_group)
        cls.college=Department.objects.create(code="CST",name="College of Science and Technology")
        cls.program=Program.objects.create(department=cls.college,code="BSCS",name="Computer Science")
        cls.term=SchoolTerm.objects.create(name="1st Semester",school_year="2026-2027",is_open=True,maximum_units=30)
        cls.student=Student.objects.create(user=cls.student_user,first_name="Alex",last_name="Sample",program=cls.program,year_level=2)
        iu=User.objects.create_user(username="instructor",password="StrongPass!123")
        cls.instructor=Instructor.objects.create(user=iu,employee_no="EMP-1",department=cls.college)
        cls.prereq=Subject.objects.create(code="CS101",title="Intro to Computing",units="3.0")
        cls.dependent=Subject.objects.create(code="CS201",title="Data Structures",units="3.0")
        cls.pre_curr=CurriculumSubject.objects.create(program=cls.program,subject=cls.prereq,year_level=1,semester=cls.term.name)
        cls.dep_curr=CurriculumSubject.objects.create(program=cls.program,subject=cls.dependent,year_level=2,semester=cls.term.name)
        cls.dep_curr.prerequisites.add(cls.prereq)
        sec1=Section.objects.create(code="1A",term=cls.term,program=cls.program,year_level=1)
        sec2=Section.objects.create(code="2A",term=cls.term,program=cls.program,year_level=2)
        cls.prereq_offering=SubjectOffering.objects.create(curriculum_subject=cls.pre_curr,section=sec1,instructor=cls.instructor,capacity=30)
        cls.dep_offering=SubjectOffering.objects.create(curriculum_subject=cls.dep_curr,section=sec2,instructor=cls.instructor,capacity=30)

    def test_student_id_generated(self):
        self.assertTrue(self.student.student_id.startswith("STU-")); self.assertEqual(len(self.student.student_id),10)

    def test_missing_prerequisite_replaced_with_prerequisite(self):
        selected, explanations, warnings=generate_initial_subjects(self.student,self.term)
        self.assertEqual([x.pk for x in selected],[self.prereq_offering.pk])
        self.assertTrue(any("CS201" in x and "CS101" in x for x in explanations)); self.assertFalse(warnings)

    def test_student_planner_loads_and_assigns_subjects(self):
        self.client.force_login(self.student_user); response=self.client.get(reverse("enrollment_planner"))
        self.assertEqual(response.status_code,200); self.assertContains(response,"CS101")

    def test_student_enrollment_portal_shows_subjects_and_pre_enrollment_form(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term)
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_enrollment_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Enrolled Subjects")
        self.assertContains(response, "CS101")
        self.assertContains(response, reverse("student_enrollment_form", args=[enrollment.pk]))
        detail = self.client.get(reverse("student_enrollment_form", args=[enrollment.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Pre-Enrollment Form / Subject List")
        self.assertContains(detail, "CS101")

    def test_student_cannot_view_another_students_enrollment_form(self):
        other_user = get_user_model().objects.create_user(username="other-student", password="StrongPass!123")
        other_user.groups.add(Group.objects.get(name="Student"))
        other = Student.objects.create(user=other_user, first_name="Taylor", last_name="Other", program=self.program)
        enrollment = Enrollment.objects.create(student=other, term=self.term)
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("student_enrollment_form", args=[enrollment.pk])).status_code, 404)

    def test_approval_automatically_generates_cor(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term)
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        for document_type in ["Grade Card", "Pre-Enrollment Form", "Clearance"]:
            StudentDocument.objects.create(student=self.student, term=self.term,
                document_type=document_type, status="VERIFIED")
        self.client.force_login(self.admin)
        response = self.client.post(reverse("enrollment_review", args=[enrollment.pk]), {"decision": "approve"})
        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, "ENROLLED")
        self.assertEqual(enrollment.cor_versions.count(), 1)
        cor = enrollment.cor_versions.get(version=1)
        self.assertEqual(cor.snapshot["subjects"][0]["code"], "CS101")

    def test_payment_verification_updates_student_billing_and_issues_revised_cor(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        fee = Fee.objects.create(name="Tuition and fees", amount=Decimal("90.00"), is_per_unit=False)
        AssessmentItem.objects.create(enrollment=enrollment, fee=fee,
            description=fee.name, amount=Decimal("90.00"))
        original_cor = issue_cor(enrollment, self.admin)

        cashier = get_user_model().objects.create_user(username="cashier", password="StrongPass!123")
        cashier_group, _ = Group.objects.get_or_create(name="Cashier")
        cashier.groups.add(cashier_group)
        payment = Payment.objects.create(enrollment=enrollment, amount=Decimal("50.00"),
            method="GCASH", reference_no="PAY-TEST-001", recorded_by=cashier)

        self.client.force_login(cashier)
        response = self.client.post(reverse("payment_verify", args=[payment.pk]), {"status": "VERIFIED"})
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.verification_status, "VERIFIED")
        self.assertEqual(enrollment.cor_versions.count(), 2)

        revised_cor = enrollment.cor_versions.get(version=2)
        self.assertEqual(original_cor.snapshot["verified_payments"], "0.00")
        self.assertEqual(revised_cor.snapshot["verified_payments"], "50.00")
        self.assertEqual(revised_cor.snapshot["balance"], "40.00")
        self.assertIn("Payment verification updated", revised_cor.reason)

        # Repeating the same verification must not create another COR version.
        self.client.post(reverse("payment_verify", args=[payment.pk]), {"status": "VERIFIED"})
        self.assertEqual(enrollment.cor_versions.count(), 2)

        self.client.force_login(self.student_user)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "50.00")
        self.assertContains(dashboard, "40.00")
        billing = self.client.get(reverse("billing_list"))
        self.assertEqual(billing.status_code, 200)
        self.assertContains(billing, "PAY-TEST-001")
        self.assertContains(billing, "View COR v2")


    def test_partial_payment_is_allowed_and_cannot_exceed_remaining_assessment(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        fee = Fee.objects.create(name="Installment assessment", amount=Decimal("100.00"), is_per_unit=False)
        AssessmentItem.objects.create(enrollment=enrollment, fee=fee, description=fee.name, amount=Decimal("100.00"))
        cashier = get_user_model().objects.create_user(username="cashier-partial", password="StrongPass!123")

        partial = PaymentForm(data={"enrollment": enrollment.pk, "amount": "35.00", "method": "GCASH", "reference_no": "PART-001"})
        self.assertTrue(partial.is_valid(), partial.errors)
        payment = partial.save(commit=False)
        payment.recorded_by = cashier
        payment.save()

        next_installment = PaymentForm(data={"enrollment": enrollment.pk, "amount": "65.00", "method": "CASH", "reference_no": "PART-002"})
        self.assertTrue(next_installment.is_valid(), next_installment.errors)

        too_much = PaymentForm(data={"enrollment": enrollment.pk, "amount": "66.00", "method": "CASH", "reference_no": "PART-003"})
        self.assertFalse(too_much.is_valid())
        self.assertIn("amount", too_much.errors)

    def test_student_can_view_and_print_cor_with_partial_payment(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        fee = Fee.objects.create(name="Tuition", amount=Decimal("100.00"), is_per_unit=False)
        AssessmentItem.objects.create(enrollment=enrollment, fee=fee, description=fee.name, amount=Decimal("100.00"))
        cashier = get_user_model().objects.create_user(username="cashier-cor-partial", password="StrongPass!123")
        Payment.objects.create(enrollment=enrollment, amount=Decimal("25.00"), method="GCASH",
            reference_no="PARTIAL-COR-001", verification_status="VERIFIED", recorded_by=cashier,
            verified_by=self.admin)
        cor = issue_cor(enrollment, self.admin)
        self.assertEqual(cor.snapshot["payment_status"], "PARTIALLY_PAID")
        self.assertEqual(cor.snapshot["verified_payments"], "25.00")
        self.assertEqual(cor.snapshot["balance"], "75.00")

        self.client.force_login(self.student_user)
        listing = self.client.get(reverse("cor_list", args=[enrollment.pk]))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "View / Print")
        printed = self.client.get(reverse("cor_print", args=[enrollment.pk, cor.version]))
        self.assertEqual(printed.status_code, 200)
        self.assertContains(printed, "Partially Paid")
        self.assertContains(printed, "75.00")

    def test_legacy_enrolled_record_gets_missing_cor_without_duplicates(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        first = ensure_cor_for_enrolled(enrollment)
        self.assertIsNotNone(first)
        self.assertEqual(enrollment.cor_versions.count(), 1)
        self.assertEqual(first.reason, "Backfilled for previously approved enrollment")
        second = ensure_cor_for_enrolled(enrollment)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(enrollment.cor_versions.count(), 1)

    def test_legacy_approved_status_gets_missing_cor(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="APPROVED")
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        cor = ensure_cor_for_enrolled(enrollment)
        self.assertIsNotNone(cor)
        self.assertEqual(enrollment.cor_versions.count(), 1)

    def test_pending_enrollment_does_not_get_cor_from_backfill(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="PENDING")
        self.assertIsNone(ensure_cor_for_enrolled(enrollment))
        self.assertEqual(enrollment.cor_versions.count(), 0)

    def test_student_portal_backfills_missing_cor_for_legacy_enrolled_record(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_enrollment_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(enrollment.cor_versions.count(), 1)
        self.assertContains(response, reverse("cor_list", args=[enrollment.pk]))

    def test_own_student_record_is_private(self):
        other=Student.objects.create(first_name="Taylor",last_name="Other",program=self.program)
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("student_detail",args=[other.pk])).status_code,403)

    def test_enrollment_validation_rejects_empty_selection(self):
        enrollment=Enrollment.objects.create(student=self.student,term=self.term)
        self.assertTrue(any("at least one subject" in x for x in validate_enrollment(enrollment)))

    def test_first_login_requires_password_change(self):
        student=Student.objects.create(first_name="Morgan",last_name="Temporary",program=self.program,year_level=1)
        created,_=create_student_portal_account(student); self.assertTrue(created); student.refresh_from_db()
        self.assertTrue(student.must_change_password); self.client.force_login(student.user)
        response=self.client.get(reverse("dashboard")); self.assertEqual(response.status_code,302); self.assertEqual(response.url,reverse("password_change"))

    def test_demo_seed_command_is_idempotent(self):
        call_command("seed_demo_data",verbosity=0); count=Department.objects.count()
        call_command("seed_demo_data",verbosity=0); self.assertEqual(Department.objects.count(),count)

    def test_demo_seed_populates_demo_records_and_credentials(self):
        call_command("seed_demo_data", verbosity=0)
        demo_user = get_user_model().objects.get(username="demo_student")
        self.assertIsNotNone(authenticate(username="demo_student", password="DemoPass!2026"))
        demo_student = Student.objects.get(user=demo_user)
        self.assertTrue(demo_student.birth_date)
        self.assertTrue(demo_student.gender)
        self.assertTrue(demo_student.phone)
        self.assertTrue(demo_student.address)
        current_term = SchoolTerm.objects.get(school_year="2026-2027", name="1st Semester")
        current_enrollment = Enrollment.objects.get(student=demo_student, term=current_term)
        self.assertEqual(
            list(current_enrollment.subjects.values_list("offering__curriculum_subject__subject__code", flat=True)),
            ["DEMO-CS102"],
        )
        self.assertTrue(current_enrollment.assessment_items.exists())
        self.assertTrue(Payment.objects.filter(enrollment=current_enrollment, verification_status="PENDING").exists())
        self.assertEqual(demo_student.documents.filter(term=current_term).count(), 3)
        self.assertTrue(Grade.objects.filter(
            enrollment_subject__enrollment__student=demo_student,
            enrollment_subject__enrollment__term__school_year="2025-2026",
            final=Decimal("2.00"),
        ).exists())


    def test_every_select_field_has_at_least_three_choices(self):
        call_command("seed_demo_data", verbosity=0)
        forms_to_check = [StudentForm(), EnrollmentForm(), PaymentForm(), StudentDocumentUploadForm()]
        excluded = {
            "enrollment-records": ["submitted_at", "approved_by", "status"],
            "assessment-items": [], "enrollment-subjects": [], "student-documents": [],
        }
        for slug, (model, _module, _title) in MANAGED_MODELS.items():
            excluded_fields = excluded.get(slug, [])
            ModelForm = forms.modelform_factory(model, fields="__all__", exclude=excluded_fields)
            forms_to_check.append(ModelForm())

        for form in forms_to_check:
            for field_name, field in form.fields.items():
                if isinstance(field, (forms.ModelChoiceField, forms.ModelMultipleChoiceField)):
                    self.assertGreaterEqual(
                        field.queryset.count(), 3,
                        f"{form.__class__.__name__}.{field_name} needs at least 3 database options",
                    )
                elif getattr(field, "choices", None) is not None and field.__class__.__name__ in {
                    "ChoiceField", "TypedChoiceField"
                }:
                    self.assertGreaterEqual(
                        len(list(field.choices)), 3,
                        f"{form.__class__.__name__}.{field_name} needs at least 3 choices",
                    )

        self.assertGreaterEqual(Department.objects.count(), 3)
        self.assertGreaterEqual(Program.objects.count(), 3)
        self.assertGreaterEqual(SchoolTerm.objects.count(), 3)
        self.assertGreaterEqual(Subject.objects.count(), 3)
        self.assertGreaterEqual(CurriculumSubject.objects.count(), 3)
        self.assertGreaterEqual(Instructor.objects.count(), 3)
        self.assertGreaterEqual(Room.objects.count(), 3)
        self.assertGreaterEqual(Section.objects.count(), 3)
        self.assertGreaterEqual(SubjectOffering.objects.count(), 3)
        self.assertGreaterEqual(Student.objects.count(), 3)
        self.assertGreaterEqual(Enrollment.objects.count(), 3)
        self.assertGreaterEqual(EnrollmentSubject.objects.count(), 3)
        self.assertGreaterEqual(Fee.objects.count(), 3)
        self.assertGreaterEqual(ClassSchedule.objects.count(), 3)
        self.assertGreaterEqual(AssessmentItem.objects.count(), 3)

    def test_excel_export(self):
        self.client.force_login(self.admin); response=self.client.get(reverse("reports")+"?format=xlsx")
        self.assertEqual(response.status_code,200); self.assertIn("spreadsheetml",response["Content-Type"])

    def test_pdf_export_if_runtime_available(self):
        self.client.force_login(self.admin)
        try: import reportlab.pdfgen.canvas
        except ImportError: self.skipTest("Validation environment includes Windows-specific Pillow binary; target OS install will supply native dependency.")
        response=self.client.get(reverse("reports")+"?format=pdf")
        self.assertEqual(response.status_code,200); self.assertEqual(response["Content-Type"],"application/pdf")


    def test_student_can_submit_payment_proof_and_cashier_can_issue_receipt(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        fee = Fee.objects.create(name="Online payment assessment", amount=Decimal("100.00"), is_per_unit=False)
        AssessmentItem.objects.create(enrollment=enrollment, fee=fee, description=fee.name, amount=Decimal("100.00"))
        self.client.force_login(self.student_user)
        proof = SimpleUploadedFile("proof.pdf", b"%PDF-1.4\nproof-data", content_type="application/pdf")
        response = self.client.post(reverse("record_payment"), {
            "enrollment": enrollment.pk, "amount": "40.00", "method": "GCASH",
            "reference_no": "GCASH-REF-001", "proof_file": proof,
        })
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(enrollment=enrollment)
        self.assertEqual(payment.verification_status, "PENDING")
        self.assertEqual(payment.recorded_by, self.student_user)
        self.assertTrue(payment.proof_file)
        self.assertFalse(payment.receipt_number)
        cashier = get_user_model().objects.create_user(username="cashier-proof", password="StrongPass!123")
        cashier_group, _ = Group.objects.get_or_create(name="Cashier")
        cashier.groups.add(cashier_group)
        self.client.force_login(cashier)
        response = self.client.post(reverse("payment_verify", args=[payment.pk]), {"status": "VERIFIED"})
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.verification_status, "VERIFIED")
        self.assertTrue(payment.receipt_number.startswith("OR-"))
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("payment_receipt", args=[payment.pk])).status_code, 200)

    def test_admission_application_approval_creates_student_and_history(self):
        response = self.client.post(reverse("admission_apply"), {
            "first_name": "Jamie", "middle_name": "", "last_name": "Applicant",
            "birth_date": "2007-01-01", "email": "jamie@example.test", "phone": "09170000000",
            "address": "Palawan", "program": self.program.pk, "term": self.term.pk,
            "admission_category": "FRESHMAN",
        })
        self.assertEqual(response.status_code, 200)
        application = AdmissionApplication.objects.get(email="jamie@example.test")
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admission_application_review", args=[application.pk]), {"decision": "APPROVED"})
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.status, "APPROVED")
        self.assertIsNotNone(application.created_student)
        self.assertTrue(application.created_student.user.check_password("Applicant"))
        self.assertTrue(application.created_student.must_change_password)
        self.assertTrue(AcademicRecord.objects.filter(student=application.created_student, record_type="ADMISSION").exists())

    def test_reports_catalog_contains_twelve_working_report_types(self):
        from .reporting import REPORTS
        self.client.force_login(self.admin)
        self.assertEqual(len(REPORTS), 12)
        for key, _label in REPORTS:
            response = self.client.get(reverse("reports"), {"report": key})
            self.assertEqual(response.status_code, 200, key)

    def test_instructor_can_only_see_and_edit_assigned_class_grades(self):
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        item = EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        other_user = get_user_model().objects.create_user(username="other-instructor", password="StrongPass!123")
        other_user.groups.add(Group.objects.get_or_create(name="Instructor")[0])
        other_instructor = Instructor.objects.create(user=other_user, employee_no="EMP-OTHER", department=self.college)
        other_subject = Subject.objects.create(code="CS301", title="Networks", units="3.0")
        other_curriculum = CurriculumSubject.objects.create(program=self.program, subject=other_subject, year_level=2, semester=self.term.name)
        other_section = Section.objects.create(code="2B", term=self.term, program=self.program, year_level=2)
        other_offering = SubjectOffering.objects.create(curriculum_subject=other_curriculum, section=other_section, instructor=other_instructor)
        other_item = EnrollmentSubject.objects.create(enrollment=enrollment, offering=other_offering)
        instructor_user = self.instructor.user
        instructor_user.groups.add(Group.objects.get_or_create(name="Instructor")[0])
        self.client.force_login(instructor_user)
        response = self.client.get(reverse("grade_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CS101")
        self.assertNotContains(response, "CS301")
        self.assertEqual(self.client.get(reverse("grade_edit", args=[other_item.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("grade_edit", args=[item.pk])).status_code, 200)

    def test_approved_scholarship_reduces_assessment_and_updates_cor(self):
        from .services import financial_totals
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        fee = Fee.objects.create(name="Scholarship fee", amount=Decimal("100.00"), is_per_unit=False)
        AssessmentItem.objects.create(enrollment=enrollment, fee=fee, description=fee.name, amount=Decimal("100.00"))
        original = issue_cor(enrollment, self.admin)
        adjustment = FinancialAdjustment.objects.create(enrollment=enrollment, kind="SCHOLARSHIP", amount=Decimal("25.00"), created_by=self.admin)
        cashier = get_user_model().objects.create_user(username="cashier-adjustment", password="StrongPass!123")
        cashier.groups.add(Group.objects.get_or_create(name="Cashier")[0])
        self.client.force_login(cashier)
        response = self.client.post(reverse("financial_adjustment_review", args=[adjustment.pk]), {"decision": "APPROVED"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(financial_totals(enrollment)["assessment"], Decimal("75.00"))
        revised = enrollment.cor_versions.order_by("-version").first()
        self.assertGreater(revised.version, original.version)
        self.assertEqual(revised.snapshot["assessment"], "75.00")


    def test_registrar_approved_add_request_updates_enrollment_and_reissues_cor(self):
        from django.utils import timezone
        from datetime import timedelta
        from .services import apply_approved_enrollment_change
        now = timezone.now()
        self.term.add_drop_opens = now - timedelta(days=1)
        self.term.add_drop_closes = now + timedelta(days=1)
        self.term.save(update_fields=["add_drop_opens", "add_drop_closes"])
        enrollment = Enrollment.objects.create(student=self.student, term=self.term, status="ENROLLED")
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=self.prereq_offering)
        original_cor = issue_cor(enrollment, self.admin)
        self.client.force_login(self.student_user)
        request_page = self.client.get(reverse("enrollment_change_request", args=[enrollment.pk]))
        self.assertEqual(request_page.status_code, 200)
        change = EnrollmentChange.objects.create(enrollment=enrollment, change_type="ADD",
            subject_code=self.dependent.code, to_offering=self.dep_offering, status="PENDING", changed_by=self.student_user,
            reason="Need the next course in my curriculum")
        apply_approved_enrollment_change(change, self.admin)
        change.refresh_from_db()
        self.assertEqual(change.status, "APPROVED")
        self.assertEqual(enrollment.subjects.count(), 2)
        revised = enrollment.cor_versions.order_by("-version").first()
        self.assertEqual(revised.version, original_cor.version + 1)
        self.assertEqual(len(revised.snapshot["subjects"]), 2)

    def test_schedule_save_rejects_same_term_room_overlap(self):
        from django.core.exceptions import ValidationError
        from datetime import time
        room = Room.objects.create(code="ROOM-LOCK", capacity=30)
        ClassSchedule.objects.create(offering=self.prereq_offering, day="0", start_time=time(8, 0), end_time=time(9, 0), room=room)
        with self.assertRaises(ValidationError):
            ClassSchedule.objects.create(offering=self.dep_offering, day="0", start_time=time(8, 30), end_time=time(9, 30), room=room)


    def test_student_self_service_password_reset_sends_email(self):
        from django.core import mail
        from django.test import override_settings
        self.student.email = "alex@example.test"
        self.student.save(update_fields=["email"])
        self.student_user.email = self.student.email
        self.student_user.save(update_fields=["email"])
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post(reverse("password_reset"), {"email": self.student.email})
            self.assertRedirects(response, reverse("password_reset_done"))
            self.assertEqual(len(mail.outbox), 1)
            import re
            match = re.search(r"http://testserver(/accounts/password/reset/[^\s]+/)", mail.outbox[0].body)
            self.assertIsNotNone(match)
            confirm_response = self.client.get(match.group(1), follow=True)
            self.assertEqual(confirm_response.status_code, 200)
            confirm_path = confirm_response.request["PATH_INFO"]
            complete_response = self.client.post(confirm_path, {
                "new_password1": "NewStrongPass!456",
                "new_password2": "NewStrongPass!456",
            })
            self.assertRedirects(complete_response, reverse("password_reset_complete"))
            self.student_user.refresh_from_db()
            self.assertTrue(self.student_user.check_password("NewStrongPass!456"))

    def test_staff_self_service_password_reset_sends_email(self):
        from django.core import mail
        from django.test import override_settings
        staff_user = get_user_model().objects.get(username="instructor")
        staff_user.email = "instructor@example.test"
        staff_user.save(update_fields=["email"])
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post(reverse("password_reset"), {"email": staff_user.email})
            self.assertRedirects(response, reverse("password_reset_done"))
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn("password/reset/", mail.outbox[0].body)
            self.assertEqual(mail.outbox[0].to, ["instructor@example.test"])

    def test_registrar_can_send_student_password_reset_link(self):
        from django.core import mail
        from django.test import override_settings
        self.student.email = "alex@example.test"
        self.student.save(update_fields=["email"])
        self.student_user.email = "old-address@example.test"
        self.student_user.save(update_fields=["email"])
        self.client.force_login(self.admin)
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self.client.post(reverse("student_send_password_reset", args=[self.student.pk]))
            self.assertRedirects(response, reverse("student_detail", args=[self.student.pk]))
            self.assertEqual(len(mail.outbox), 1)
            self.student_user.refresh_from_db()
            self.assertEqual(self.student_user.email, "alex@example.test")
            self.assertIn("password/reset/", mail.outbox[0].body)

    def test_student_cannot_trigger_staff_password_reset_action(self):
        response = self.client.post(reverse("student_send_password_reset", args=[self.student.pk]))
        self.assertEqual(response.status_code, 302)  # anonymous users are sent to login
        self.client.force_login(self.student_user)
        response = self.client.post(reverse("student_send_password_reset", args=[self.student.pk]))
        self.assertEqual(response.status_code, 403)
