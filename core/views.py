from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Department, Program, Student, SchoolTerm, Subject, CurriculumSubject,
    Instructor, Room, Section, SubjectOffering, ClassSchedule, Enrollment,
    EnrollmentSubject, Fee, AssessmentItem, Payment, Grade, AuditLog, StudentDocument, EnrollmentChange, CORVersion,
    AcademicRecord, FinancialAdjustment, AdmissionApplication,
)
from .forms import StudentForm, EnrollmentForm, PaymentForm, StudentDocumentUploadForm, StudentPaymentSubmissionForm, GradeForm, FinancialAdjustmentForm, EnrollmentChangeRequestForm, AdmissionApplicationForm
from .permissions import can_access
from .services import (enrollment_period_open, add_drop_period_open, save_initial_subjects, validate_enrollment, recalculate_assessment, issue_cor, ensure_cor_for_enrolled, missing_required_documents, refresh_cor_after_payment, financial_totals)
from django.core.paginator import Paginator

def guard(request, module):
    if not can_access(request.user, module):
        return HttpResponseForbidden("You do not have permission to access this module.")
    return None


def create_student_portal_account(student):
    """Create a student login: username=Student ID, initial password=last name."""
    if student.user_id:
        return False, "This student is already linked to a login account."
    User = get_user_model()
    if User.objects.filter(username=student.student_id).exists():
        return False, f"Username {student.student_id} already exists. Resolve the existing account before linking it."
    with transaction.atomic():
        user = User.objects.create_user(
            username=student.student_id,
            password=student.last_name,
            email=student.email or "",
            first_name=student.first_name,
            last_name=student.last_name,
        )
        group, _ = Group.objects.get_or_create(name="Student")
        user.groups.add(group)
        student.user = user
        student.must_change_password = True
        student.save(update_fields=["user", "must_change_password"])
    return True, f"Student portal account created. Username: {student.student_id}; initial password: the student's last name."


def can_manage(request):
    return request.user.is_superuser or request.user.groups.filter(
        name__in=["Administrator", "Registrar"]
    ).exists()


def admission_apply(request):
    """Public prospective-student admission application intake."""
    form = AdmissionApplicationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        application = form.save()
        messages.success(request, "Your admission application was submitted. Keep your application details for follow-up with the Registrar.")
        return render(request, "core/admission_submitted.html", {"application": application})
    return render(request, "core/admission_apply.html", {"form": form})


@login_required
def admission_applications(request):
    if not can_manage(request):
        return HttpResponseForbidden("Only the Registrar or Administrator can review admission applications.")
    applications = AdmissionApplication.objects.select_related("program", "term", "reviewed_by", "created_student").order_by("-created_at")
    return render(request, "core/admission_applications.html", {"applications": applications})


@transaction.atomic
@transaction.atomic
@login_required
@require_POST
def admission_application_review(request, pk):
    if not can_manage(request):
        return HttpResponseForbidden("Only the Registrar or Administrator can review admission applications.")
    application = get_object_or_404(AdmissionApplication.objects.select_for_update(), pk=pk)
    decision = request.POST.get("decision")
    if application.status != "PENDING":
        messages.warning(request, "This application has already been reviewed.")
        return redirect("admission_applications")
    if decision == "APPROVED":
        with transaction.atomic():
            student = Student.objects.create(first_name=application.first_name, middle_name=application.middle_name,
                last_name=application.last_name, birth_date=application.birth_date, email=application.email,
                phone=application.phone, address=application.address, program=application.program,
                admission_category=application.admission_category, year_level=1)
            AcademicRecord.objects.create(student=student, term=application.term, program=student.program,
                year_level=1, record_type="ADMISSION", status="ADMITTED", effective_date=timezone.localdate(),
                notes=f"Approved admission application #{application.pk}.", created_by=request.user)
            created, account_message = create_student_portal_account(student)
            application.created_student = student
            application.status = "APPROVED"
            application.notes = (application.notes + "\n" + account_message).strip()
    elif decision == "REJECTED":
        application.status = "REJECTED"
    else:
        return HttpResponseForbidden("Invalid decision.")
    application.reviewed_by = request.user
    application.reviewed_at = timezone.now()
    application.save(update_fields=["created_student", "status", "notes", "reviewed_by", "reviewed_at"])
    AuditLog.objects.create(user=request.user, action=f"Admission application {decision.lower()}", object_type="AdmissionApplication", object_id=str(application.pk))
    messages.success(request, "Admission application approved and student account created." if decision == "APPROVED" else "Admission application rejected.")
    return redirect("admission_applications")


@login_required
def dashboard(request):
    groups = set(request.user.groups.values_list("name", flat=True))
    role = "Administrator" if request.user.is_superuser else next((x for x in ["Administrator", "Registrar", "Cashier", "Instructor", "Student"] if x in groups), "User")
    own_student = Student.objects.filter(user=request.user).first()
    student_finances = {"assessed_total": Decimal("0"), "balance_total": Decimal("0"),
                        "pending_payment_count": 0}
    if role == "Student":
        own_enrollments = own_student.enrollments.all() if own_student else Enrollment.objects.none()
        finance_rows = [financial_totals(e) for e in own_enrollments] if own_student else []
        assessed_total = sum((x["assessment"] for x in finance_rows), Decimal("0.00"))
        paid_total = sum((x["verified_payments"] for x in finance_rows), Decimal("0.00"))
        pending_payment_count = Payment.objects.filter(enrollment__student=own_student,
            verification_status="PENDING").count() if own_student else 0
        student_finances = {"assessed_total": assessed_total,
                            "balance_total": assessed_total - paid_total,
                            "pending_payment_count": pending_payment_count}
        stats = {"students": 1 if own_student else 0, "enrollments": own_enrollments.count(),
                 "pending": own_enrollments.filter(status="PENDING").count(),
                 "collections": paid_total}
    else:
        stats = {"students": Student.objects.count(), "enrollments": Enrollment.objects.count(),
                 "pending": Enrollment.objects.filter(status="PENDING").count(),
                 "collections": Payment.objects.filter(verification_status="VERIFIED").aggregate(v=Sum("amount"))["v"] or Decimal("0")}
    return render(request, "core/dashboard.html", {"role": role, "own_student": own_student,
        "own_enrollments": own_student.enrollments.count() if own_student else 0,
        **student_finances, **stats})


@login_required
def student_list(request):
    denied = guard(request, "students")
    if denied:
        return denied
    terms = SchoolTerm.objects.order_by("-school_year", "-id")
    term_id = request.GET.get("term")
    selected_term = terms.filter(pk=term_id).first() if term_id else terms.filter(is_open=True).first()
    status = request.GET.get("status", "")
    students = Student.objects.select_related("program", "program__department").all()
    if request.user.groups.filter(name="Student").exists():
        students = students.filter(user=request.user)
    search = request.GET.get("q", "").strip()
    if search:
        students = students.filter(
            Q(student_id__icontains=search) | Q(first_name__icontains=search)
            | Q(middle_name__icontains=search) | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )
    if request.GET.get("program"):
        students = students.filter(program_id=request.GET["program"])
    if request.GET.get("year"):
        students = students.filter(year_level=request.GET["year"])
    if selected_term:
        enrolled_ids = Enrollment.objects.filter(term=selected_term, status="ENROLLED").values_list("student_id", flat=True)
        if status == "ENROLLED":
            students = students.filter(pk__in=enrolled_ids)
        elif status == "UNENROLLED":
            students = students.exclude(pk__in=enrolled_ids)
        rows = []
    for student in students.order_by("student_id"):
        enrollment = Enrollment.objects.filter(
            student=student,
            term=selected_term
        ).first() if selected_term else None

        rows.append({
            "student": student,
            "status": (
                "ENROLLED"
                if enrollment and enrollment.status == "ENROLLED"
                else "UNENROLLED"
            ) if selected_term else "",
            "enrollment": enrollment
        })

    paginator = Paginator(rows, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "core/student_list.html", {
        "rows": page_obj,
        "page_obj": page_obj,
        "terms": terms,
        "selected_term": selected_term,
        "programs": Program.objects.order_by("code"),
        "search": search,
        "selected_status": status,
        "selected_program": request.GET.get("program", ""),
        "selected_year": request.GET.get("year", ""),
        "can_manage": can_manage(request),
    })


@login_required
def student_create(request):
    denied = guard(request, "students")
    if denied:
        return denied
    if not can_manage(request):
        return HttpResponseForbidden("Only the Administrator or Registrar can register students.")
    form = StudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        AcademicRecord.objects.create(student=student, program=student.program, year_level=student.year_level,
            record_type="ADMISSION", status="REGISTERED", effective_date=timezone.localdate(),
            notes=f"Admission category: {student.get_admission_category_display()}", created_by=request.user)
        AuditLog.objects.create(user=request.user, action="Created student", object_type="Student", object_id=student.pk)
        try:
            created, account_message = create_student_portal_account(student)
            if created:
                messages.success(request, account_message)
            else:
                messages.warning(request, account_message)
        except IntegrityError:
            messages.warning(request, "Student was registered, but the portal account could not be created because the Student ID username is already in use.")
        messages.success(request, f"Student registered. ID: {student.student_id}")
        return redirect("student_detail", pk=student.pk)
    return render(request, "core/form.html", {"form": form, "title": "Student Registration", "cancel_url": reverse("student_list")})


@login_required
def student_detail(request, pk):
    denied = guard(request, "students")
    if denied:
        return denied
    student = get_object_or_404(Student.objects.select_related("program__department"), pk=pk)
    if request.user.groups.filter(name="Student").exists() and student.user_id != request.user.id:
        return HttpResponseForbidden("You can only view your own student record.")
    enrollments = student.enrollments.select_related("term").prefetch_related("payments", "assessment_items").order_by("-submitted_at")
    academic_records = student.academic_records.select_related("term", "program", "created_by")
    return render(request, "core/student_detail.html", {"student": student, "enrollments": enrollments,
        "academic_records": academic_records, "can_manage": can_manage(request)})


@login_required
@require_POST
def student_create_portal_account(request, pk):
    denied = guard(request, "students")
    if denied:
        return denied
    if not can_manage(request):
        return HttpResponseForbidden("Only the Administrator or Registrar can create student portal accounts.")
    student = get_object_or_404(Student, pk=pk)
    try:
        created, account_message = create_student_portal_account(student)
        if created:
            AuditLog.objects.create(user=request.user, action="Created student portal account", object_type="Student", object_id=student.pk)
            messages.success(request, account_message)
        else:
            messages.warning(request, account_message)
    except IntegrityError:
        messages.error(request, "The account could not be created because this Student ID is already used as a username.")
    return redirect("student_detail", pk=student.pk)


@login_required
def student_edit(request, pk):
    denied = guard(request, "students")
    if denied:
        return denied
    if not can_manage(request):
        return HttpResponseForbidden("Only the Administrator or Registrar can edit student records.")
    student = get_object_or_404(Student, pk=pk)
    previous_program_id, previous_year, previous_standing = student.program_id, student.year_level, student.enrollment_standing
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        student = form.save()
        if previous_program_id != student.program_id:
            AcademicRecord.objects.create(student=student, program=student.program, year_level=student.year_level,
                record_type="TRANSFER", status="PROGRAM_CHANGED", effective_date=timezone.localdate(),
                notes="Program updated by Registrar/Administrator.", created_by=request.user)
        if previous_year != student.year_level:
            AcademicRecord.objects.create(student=student, program=student.program, year_level=student.year_level,
                record_type="YEAR_LEVEL", status="UPDATED", effective_date=timezone.localdate(),
                notes=f"Year level changed from {previous_year} to {student.year_level}.", created_by=request.user)
        if previous_standing != student.enrollment_standing:
            AcademicRecord.objects.create(student=student, program=student.program, year_level=student.year_level,
                record_type="STANDING", status=student.get_enrollment_standing_display(), effective_date=timezone.localdate(),
                notes=f"Academic standing changed from {previous_standing}.", created_by=request.user)
        AuditLog.objects.create(user=request.user, action="Updated student", object_type="Student", object_id=student.pk)
        messages.success(request, "Student record updated.")
        return redirect("student_detail", pk=student.pk)
    return render(request, "core/form.html", {"form": form, "title": "Edit Student", "cancel_url": reverse("student_detail", args=[student.pk])})


@login_required
@require_POST
def student_delete(request, pk):
    denied = guard(request, "students")
    if denied:
        return denied
    if not can_manage(request):
        return HttpResponseForbidden("Only the Administrator or Registrar can delete student records.")
    student = get_object_or_404(Student, pk=pk)
    try:
        with transaction.atomic():
            AuditLog.objects.create(user=request.user, action="Deleted student", object_type="Student", object_id=student.pk)
            student.delete()
        messages.success(request, "Student record deleted.")
    except Exception:
        messages.error(request, "This student cannot be deleted because related enrollment or financial records exist. Keep the record and update its status instead.")
    return redirect("student_list")


@login_required
def academic_overview(request):
    denied = guard(request, "academics")
    if denied:
        return denied
    return render(request, "core/academic_overview.html", {
        "programs": Program.objects.select_related("department"), "subjects": Subject.objects.all(),
        "terms": SchoolTerm.objects.all(), "colleges": Department.objects.all(),
        "curricula": CurriculumSubject.objects.select_related("program", "subject"),
        "instructors": Instructor.objects.select_related("user", "department"),
        "rooms": Room.objects.all(), "sections": Section.objects.select_related("program", "term"),
        "offerings": SubjectOffering.objects.select_related("curriculum_subject__subject", "section"),
        "fees": Fee.objects.all(),
    })


# Website-based maintenance pages. These keep users out of Django Admin for routine CRUD.
MANAGED_MODELS = {
    "colleges": (Department, "academics", "Colleges"),
    "programs": (Program, "academics", "Academic Programs"),
    "terms": (SchoolTerm, "academics", "School Terms"),
    "subjects": (Subject, "academics", "Subjects"),
    "curriculum": (CurriculumSubject, "academics", "Curriculum Subjects"),
    "instructors": (Instructor, "academics", "Instructors"),
    "rooms": (Room, "academics", "Rooms"),
    "sections": (Section, "academics", "Sections"),
    "offerings": (SubjectOffering, "academics", "Subject Offerings"),
    "schedules": (ClassSchedule, "schedules", "Class Schedules"),
    "fees": (Fee, "billing", "Fees"),
    "enrollment-records": (Enrollment, "enrollment", "Enrollment Records"),
    "grades-records": (Grade, "grades", "Grade Records"),
    "assessment-items": (AssessmentItem, "billing", "Assessment Items"),
    "enrollment-subjects": (EnrollmentSubject, "enrollment", "Enrolled Subjects"),
    "student-documents": (StudentDocument, "students", "Student Documents"),
    "academic-history": (AcademicRecord, "students", "Academic History Records"),
}


def managed_model(slug):
    if slug not in MANAGED_MODELS:
        from django.http import Http404
        raise Http404("Unknown management section")
    return MANAGED_MODELS[slug]


@login_required
def managed_list(request, slug):
    model, module, title = managed_model(slug)
    denied = guard(request, module)
    if denied:
        return denied
    qs = model.objects.all().order_by("pk")
    if request.user.groups.filter(name="Student").exists():
        if model is Enrollment:
            qs = qs.filter(student__user=request.user)
        elif model is EnrollmentSubject:
            qs = qs.filter(enrollment__student__user=request.user)
        elif model is AssessmentItem:
            qs = qs.filter(enrollment__student__user=request.user)
        elif model is Grade:
            qs = qs.filter(enrollment_subject__enrollment__student__user=request.user)
        elif model is Payment:
            qs = qs.filter(enrollment__student__user=request.user)
        elif model is StudentDocument:
            qs = qs.filter(student__user=request.user)
        elif model is AcademicRecord:
            qs = qs.filter(student__user=request.user)
        elif model is FinancialAdjustment:
            qs = qs.filter(enrollment__student__user=request.user)
    return render(request, "core/managed_list.html", {"slug": slug, "title": title, "objects": qs, "can_manage": can_manage(request)})


@login_required
def managed_form(request, slug, pk=None):
    model, module, title = managed_model(slug)
    denied = guard(request, module)
    if denied:
        return denied
    if not can_manage(request):
        return HttpResponseForbidden("Only the Administrator or Registrar can maintain these records.")
    instance = get_object_or_404(model, pk=pk) if pk is not None else None
    excluded = []
    if model is Enrollment:
        excluded = ["submitted_at", "approved_by", "status"]
    if model is Payment:
        excluded = ["recorded_by", "paid_at"]
    if model is AuditLog:
        excluded = ["user", "created_at"]
    if model is AcademicRecord:
        excluded = ["created_by", "created_at"]
    if model is FinancialAdjustment:
        excluded = ["created_by", "reviewed_by", "reviewed_at", "status"]
    ModelForm = forms.modelform_factory(model, fields="__all__", exclude=excluded, widgets={
        "starts_on": forms.DateInput(attrs={"type": "date"}),
        "ends_on": forms.DateInput(attrs={"type": "date"}),
        "start_time": forms.TimeInput(attrs={"type": "time"}),
        "end_time": forms.TimeInput(attrs={"type": "time"}),
    })
    form = ModelForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        AuditLog.objects.create(user=request.user, action=("Updated " if instance else "Created ") + title, object_type=model.__name__, object_id=obj.pk)
        messages.success(request, f"{title[:-1] if title.endswith('s') else title} saved.")
        return redirect("managed_list", slug=slug)
    return render(request, "core/form.html", {"form": form, "title": ("Edit " if instance else "Add ") + title, "cancel_url": reverse("managed_list", args=[slug])})


@login_required
@require_POST
def managed_delete(request, slug, pk):
    model, module, title = managed_model(slug)
    denied = guard(request, module)
    if denied:
        return denied
    if not can_manage(request):
        return HttpResponseForbidden("Only the Administrator or Registrar can delete these records.")
    obj = get_object_or_404(model, pk=pk)
    try:
        with transaction.atomic():
            AuditLog.objects.create(user=request.user, action="Deleted " + title, object_type=model.__name__, object_id=obj.pk)
            obj.delete()
        messages.success(request, "Record deleted.")
    except Exception:
        messages.error(request, "This record is being used by other records and cannot be deleted.")
    return redirect("managed_list", slug=slug)


@login_required
def student_enrollment_portal(request):
    """A single student-facing page for enrollment status, subjects, forms and CORs."""
    denied = guard(request, "enrollment")
    if denied:
        return denied
    if not request.user.groups.filter(name="Student").exists():
        return HttpResponseForbidden("This page is available through a student portal account.")
    student = get_object_or_404(Student, user=request.user)
    enrollments = (Enrollment.objects.filter(student=student)
        .select_related("term", "approved_by")
        .prefetch_related("subjects__offering__curriculum_subject__subject",
                          "subjects__offering__section",
                          "subjects__offering__instructor__user",
                          "cor_versions")
        .order_by("-term__school_year", "-term__id"))
    # Repair legacy approved records the first time a student opens this page.
    for enrollment in enrollments:
        if enrollment.status in ["APPROVED", "ENROLLED"] and not enrollment.cor_versions.exists():
            ensure_cor_for_enrolled(enrollment)
            # Drop the prefetched empty relation so the template sees the new COR.
            getattr(enrollment, "_prefetched_objects_cache", {}).pop("cor_versions", None)
        if enrollment.status in ["APPROVED", "ENROLLED"]:
            totals = financial_totals(enrollment)
            enrollment.assessed_total = totals["assessment"]
            enrollment.verified_total = totals["verified_payments"]
            enrollment.balance_total = totals["balance"]
            enrollment.payment_status_label = totals["payment_status"].replace("_", " ").title()
    open_term = SchoolTerm.objects.filter(is_open=True).order_by("-id").first()
    return render(request, "core/student_enrollment_portal.html", {
        "student": student,
        "enrollments": enrollments,
        "open_term": open_term,
        "open_enrollment": enrollments.filter(term=open_term).first() if open_term else None,
        "academic_records": student.academic_records.select_related("term", "program"),
    })


@login_required
def student_enrollment_form(request, pk):
    """Read-only copy of the student's submitted/approved pre-enrollment selections."""
    denied = guard(request, "enrollment")
    if denied:
        return denied
    if not request.user.groups.filter(name="Student").exists():
        return HttpResponseForbidden("This form is available through a student portal account.")
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "student__program", "term", "approved_by")
            .prefetch_related("subjects__offering__curriculum_subject__subject",
                              "subjects__offering__section",
                              "subjects__offering__instructor__user",
                              "subjects__offering__schedules__room", "cor_versions"),
        pk=pk, student__user=request.user,
    )
    if enrollment.status in ["APPROVED", "ENROLLED"] and not enrollment.cor_versions.exists():
        ensure_cor_for_enrolled(enrollment, request.user)
        getattr(enrollment, "_prefetched_objects_cache", {}).pop("cor_versions", None)
    items = enrollment.subjects.all()
    total_units = sum((item.offering.curriculum_subject.subject.units for item in items), Decimal("0"))
    return render(request, "core/student_enrollment_form.html", {
        "enrollment": enrollment,
        "items": items,
        "total_units": total_units,
        "latest_cor": enrollment.cor_versions.first(),
    })


@login_required
def enrollment_list(request):
    denied = guard(request, "enrollment")
    if denied:
        return denied
    qs = Enrollment.objects.select_related("student", "term").order_by("-submitted_at")
    if request.user.groups.filter(name="Student").exists():
        qs = qs.filter(student__user=request.user)
    return render(request, "core/enrollment_list.html", {"enrollments": qs, "can_manage": can_manage(request)})


@login_required
def enrollment_create(request):
    denied = guard(request, "enrollment")
    if denied:
        return denied
    if request.user.groups.filter(name="Student").exists():
        return redirect("enrollment_planner")
    form = EnrollmentForm(request.POST or None)
    if request.user.groups.filter(name="Student").exists():
        form.fields["student"].queryset = Student.objects.filter(user=request.user)
    if request.method == "POST" and form.is_valid():
        enrollment = form.save(commit=False)
        if request.user.groups.filter(name="Student").exists():
            enrollment.student = Student.objects.get(user=request.user)
        enrollment.save()
        AuditLog.objects.create(user=request.user, action="Submitted enrollment", object_type="Enrollment", object_id=enrollment.pk)
        messages.success(request, "Enrollment application submitted. Registrar review is required.")
        return redirect("enrollment_list")
    return render(request, "core/form.html", {"form": form, "title": "New Enrollment Application", "cancel_url": reverse("enrollment_list")})


@login_required
def billing_list(request):
    denied = guard(request, "billing")
    if denied:
        return denied
    enrollments = Enrollment.objects.select_related("student", "term")
    is_student = request.user.groups.filter(name="Student").exists()
    can_verify = request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()
    if is_student:
        enrollments = enrollments.filter(student__user=request.user)
    rows = []
    for e in enrollments.prefetch_related("payments", "cor_versions", "financial_adjustments"):
        totals = financial_totals(e)
        rows.append({"enrollment": e, "assessed": totals["assessment"], "gross_assessed": totals["gross_assessment"],
            "scholarships": totals["scholarships"], "refunds": totals["refunds"], "paid": totals["verified_payments"],
            "balance": totals["balance"], "payment_status": totals["payment_status"],
            "pending": e.payments.filter(verification_status="PENDING").order_by("-paid_at"),
            "verified_payments": e.payments.filter(verification_status="VERIFIED").order_by("-verified_at"),
            "rejected_payments": e.payments.filter(verification_status="REJECTED").order_by("-verified_at"),
            "adjustments": e.financial_adjustments.all(), "latest_cor": e.cor_versions.first()})
    return render(request, "core/billing_list.html", {"rows": rows, "can_verify": can_verify, "is_student": is_student})


@transaction.atomic
@login_required
def record_payment(request):
    denied = guard(request, "billing")
    if denied:
        return denied
    is_student = request.user.groups.filter(name="Student").exists()
    is_cashier = request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()
    if is_student:
        student = get_object_or_404(Student, user=request.user)
        form = StudentPaymentSubmissionForm(request.POST or None, request.FILES or None, student=student)
    elif is_cashier:
        form = PaymentForm(request.POST or None)
        form.fields["enrollment"].queryset = Enrollment.objects.filter(status__in=["APPROVED", "ENROLLED"])
    else:
        return HttpResponseForbidden("Only students may submit online payment proof; Cashiers and Administrators may record payments.")
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.recorded_by = request.user
        payment.verification_status = "PENDING"
        payment.verified_by = None
        payment.verified_at = None
        payment.save()
        AuditLog.objects.create(user=request.user, action="Submitted payment proof" if is_student else "Recorded payment for verification",
            object_type="Payment", object_id=payment.pk)
        messages.success(request, "Payment submitted for Cashier/Administrator verification. Your balance will change only after approval.")
        return redirect("billing_list")
    return render(request, "core/form.html", {"form": form,
        "title": "Submit Online Payment Proof" if is_student else "Record Payment",
        "cancel_url": reverse("billing_list"), "multipart": is_student})


@login_required
def schedule_list(request):
    denied = guard(request, "schedules")
    if denied:
        return denied
    schedules = ClassSchedule.objects.select_related("room", "offering__curriculum_subject__subject", "offering__instructor", "offering__section")
    if request.user.groups.filter(name="Instructor").exists() and not request.user.is_superuser:
        schedules = schedules.filter(offering__instructor__user=request.user)
    return render(request, "core/schedule_list.html", {"schedules": schedules})


@login_required
def grade_list(request):
    denied = guard(request, "grades")
    if denied:
        return denied
    grades = Grade.objects.select_related("enrollment_subject__enrollment__student", "enrollment_subject__enrollment__term",
        "enrollment_subject__offering__curriculum_subject__subject", "enrollment_subject__offering__instructor__user")
    is_student = request.user.groups.filter(name="Student").exists()
    is_instructor = request.user.groups.filter(name="Instructor").exists()
    can_edit = request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Instructor"]).exists()
    if is_student:
        grades = grades.filter(enrollment_subject__enrollment__student__user=request.user)
    elif is_instructor and not request.user.is_superuser:
        instructor = get_object_or_404(Instructor, user=request.user)
        assigned = EnrollmentSubject.objects.filter(offering__instructor=instructor, enrollment__status__in=["APPROVED", "ENROLLED"])
        for item in assigned:
            Grade.objects.get_or_create(enrollment_subject=item)
        grades = grades.filter(enrollment_subject__offering__instructor=instructor)
    return render(request, "core/grade_list.html", {"grades": grades.order_by("enrollment_subject__enrollment__term", "enrollment_subject__enrollment__student__student_id"),
        "can_edit": can_edit and not is_student, "is_instructor": is_instructor})


@login_required
def grade_edit(request, pk):
    denied = guard(request, "grades")
    if denied:
        return denied
    item = get_object_or_404(EnrollmentSubject.objects.select_related("enrollment__student", "offering__instructor__user", "offering__curriculum_subject__subject"), pk=pk)
    is_admin = request.user.is_superuser or request.user.groups.filter(name="Administrator").exists()
    if not is_admin and item.offering.instructor.user_id != request.user.id:
        return HttpResponseForbidden("Instructors may only encode grades for their assigned offerings.")
    if item.enrollment.status not in ["APPROVED", "ENROLLED"]:
        return HttpResponseForbidden("Grades can only be encoded for approved/enrolled records.")
    grade, _ = Grade.objects.get_or_create(enrollment_subject=item)
    form = GradeForm(request.POST or None, instance=grade)
    if request.method == "POST" and form.is_valid():
        form.save()
        AuditLog.objects.create(user=request.user, action="Encoded/updated grade", object_type="Grade", object_id=str(grade.pk))
        messages.success(request, "Grade saved.")
        return redirect("grade_list")
    return render(request, "core/form.html", {"form": form, "title": f"Grade · {item.offering.curriculum_subject.subject.code} · {item.enrollment.student}", "cancel_url": reverse("grade_list")})


@login_required
def reports(request):
    denied = guard(request, "reports")
    if denied:
        return denied
    from .reporting import REPORTS, build_report
    report_type = request.GET.get("report", "enrollments")
    if report_type not in dict(REPORTS):
        report_type = "enrollments"
    headers, data = build_report(report_type, request.GET.get("term") or None,
        request.GET.get("program") or None, request.GET.get("status") or None)
    export_format = request.GET.get("format")
    safe_name = report_type.replace("_", "-")
    if export_format == "csv":
        import csv
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-report.csv"'
        writer = csv.writer(response); writer.writerow(headers); writer.writerows(data)
        return response
    if export_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        workbook = Workbook(); sheet = workbook.active; sheet.title = "Report"; sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="C84E08")
        for row in data: sheet.append(row)
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(max(max(len(str(c.value or "")) for c in column)+2, 12), 42)
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-report.xlsx"'; workbook.save(response)
        return response
    if export_format == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import utils
        from io import BytesIO
        buffer = BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4)); styles = getSampleStyleSheet()
        content = [Paragraph("PalSU · " + dict(REPORTS)[report_type], styles["Title"]), Spacer(1, 12)]
        table = Table([[str(v) for v in headers]] + [[str(v) for v in row] for row in data], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#C84E08")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#E7C8AE")),
            ("FONTSIZE",(0,0),(-1,-1),7), ("VALIGN",(0,0),(-1,-1),"TOP")]))
        content.append(table); doc.build(content)
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-report.pdf"'
        return response
    collections = Payment.objects.filter(verification_status="VERIFIED").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return render(request, "core/reports.html", {"summary": data, "headers": headers, "report_types": REPORTS,
        "selected_report": report_type, "collections": collections, "terms": SchoolTerm.objects.all(),
        "programs": Program.objects.all(), "selected_term": request.GET.get("term", ""),
        "selected_program": request.GET.get("program", ""), "selected_status": request.GET.get("status", "")})


@transaction.atomic
@login_required
def enrollment_planner(request):
    denied = guard(request, "enrollment")
    if denied: return denied
    if not request.user.groups.filter(name="Student").exists():
        return HttpResponseForbidden("The subject planner is available through a student portal account.")
    student = get_object_or_404(Student, user=request.user, account_status="ACTIVE")
    term = SchoolTerm.objects.filter(is_open=True).order_by("-id").first()
    if not term:
        messages.warning(request, "There is no currently open enrollment term."); return redirect("dashboard")
    enrollment, created = Enrollment.objects.get_or_create(student=student, term=term,
        defaults={"enrollment_type": student.admission_category if student.admission_category in dict(Enrollment.TYPE) else "REGULAR"})
    if created or not enrollment.subjects.exists():
        if enrollment.status == "PENDING" and enrollment_period_open(term):
            explanations, warnings = save_initial_subjects(enrollment, request.user)
            for item in explanations: messages.info(request, item)
            for item in warnings: messages.warning(request, item)
    if request.method == "POST":
        action = request.POST.get("action")
        if enrollment.status not in ["PENDING", "REJECTED"]:
            messages.error(request, "This enrollment is no longer an editable draft."); return redirect("enrollment_planner")
        if not enrollment_period_open(term) and not add_drop_period_open(term):
            messages.error(request, "The enrollment or add/drop period is closed."); return redirect("enrollment_planner")
        if action == "drop":
            item = get_object_or_404(EnrollmentSubject, pk=request.POST.get("item"), enrollment=enrollment)
            code = item.offering.curriculum_subject.subject.code
            EnrollmentChange.objects.create(enrollment=enrollment, change_type="DROP", subject_code=code,
                from_offering=item.offering, reason=request.POST.get("reason", "").strip(), changed_by=request.user)
            item.delete(); messages.success(request, f"{code} removed from your proposed subjects.")
        elif action == "add":
            offering = get_object_or_404(SubjectOffering.objects.select_for_update().select_related("curriculum_subject__subject", "section"),
                pk=request.POST.get("offering"), section__term=term, section__program=student.program, curriculum_subject__year_level__lte=student.year_level)
            selected_ids = list(enrollment.subjects.values_list("offering_id", flat=True))
            selected = list(SubjectOffering.objects.filter(pk__in=selected_ids).prefetch_related("schedules"))
            if enrollment.subjects.filter(offering__curriculum_subject__subject=offering.curriculum_subject.subject).exists():
                messages.error(request, "That subject is already in your proposed list.")
            elif not _planner_add_allowed(enrollment, offering, selected):
                messages.error(request, "This offering is full, conflicts with your schedule, or has unmet prerequisites.")
            else:
                EnrollmentSubject.objects.create(enrollment=enrollment, offering=offering)
                EnrollmentChange.objects.create(enrollment=enrollment, change_type="ADD", subject_code=offering.curriculum_subject.subject.code,
                    to_offering=offering, reason="Student added subject", changed_by=request.user)
                messages.success(request, "Subject added.")
        elif action == "section":
            item = get_object_or_404(EnrollmentSubject, pk=request.POST.get("item"), enrollment=enrollment)
            new_offering = get_object_or_404(SubjectOffering.objects.select_related("curriculum_subject__subject", "section"),
                pk=request.POST.get("offering"), curriculum_subject__subject=item.offering.curriculum_subject.subject,
                section__term=term, section__program=student.program)
            selected_ids = EnrollmentSubject.objects.filter(enrollment=enrollment).exclude(pk=item.pk).values_list("offering_id", flat=True)
            selected = list(SubjectOffering.objects.filter(pk__in=selected_ids).prefetch_related("schedules"))
            if not _planner_add_allowed(enrollment, new_offering, selected):
                messages.error(request, "The selected section is full or conflicts with your timetable.")
            else:
                old = item.offering; item.offering = new_offering; item.save(update_fields=["offering"])
                EnrollmentChange.objects.create(enrollment=enrollment, change_type="SECTION", subject_code=new_offering.curriculum_subject.subject.code,
                    from_offering=old, to_offering=new_offering, reason="Student changed section", changed_by=request.user)
                messages.success(request, "Section updated.")
        elif action == "submit":
            errors = []
            # Lock selected offering rows in a stable order while validating/committing seat claims.
            list(SubjectOffering.objects.select_for_update().filter(
                pk__in=enrollment.subjects.values_list("offering_id", flat=True)).order_by("pk"))
            if not enrollment_period_open(term): errors.append("The enrollment period is not currently open.")
            errors.extend(validate_enrollment(enrollment))
            if errors:
                for error in errors: messages.error(request, error)
            else:
                enrollment.status = "PENDING"; enrollment.save(update_fields=["status"])
                recalculate_assessment(enrollment)
                AuditLog.objects.create(user=request.user, action="Submitted pre-enrollment form", object_type="Enrollment", object_id=str(enrollment.pk))
                messages.success(request, "Your pre-enrollment form has been submitted for Registrar review.")
                return redirect("enrollment_list")
        return redirect("enrollment_planner")
    recalculate_assessment(enrollment)
    offerings = SubjectOffering.objects.filter(section__term=term, section__program=student.program).select_related(
        "curriculum_subject__subject", "section", "instructor__user").prefetch_related("schedules")
    selected_ids = enrollment.subjects.values_list("offering_id", flat=True)
    available = offerings.exclude(pk__in=selected_ids)
    finance = financial_totals(enrollment)
    assessment = finance["assessment"]
    paid = finance["verified_payments"]
    items = enrollment.subjects.select_related("offering__curriculum_subject__subject", "offering__section", "offering__instructor__user").prefetch_related("offering__schedules")
    units = sum((x.offering.curriculum_subject.subject.units for x in items), Decimal("0"))
    return render(request, "core/enrollment_planner.html", {"student": student, "term": term, "enrollment": enrollment,
        "items": items, "offerings": available, "assessment": assessment, "paid": paid, "balance": assessment-paid,
        "total_units": units, "can_submit": enrollment.status in ["PENDING", "REJECTED"]})

def _planner_add_allowed(enrollment, offering, selected_offerings):
    from .services import _offering_has_seat, _offering_conflicts, completed_subject_ids
    if not _offering_has_seat(offering, excluding_enrollment=enrollment) or _offering_conflicts(offering, selected_offerings): return False
    completed = completed_subject_ids(enrollment.student, enrollment.term)
    cart = {x.curriculum_subject.subject_id for x in selected_offerings}
    return all(p.pk in completed or p.pk in cart for p in offering.curriculum_subject.prerequisites.all())

@transaction.atomic
@login_required
@require_POST
def enrollment_review(request, pk):
    denied = guard(request, "enrollment")
    if denied: return denied
    if not (request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Registrar"]).exists()):
        return HttpResponseForbidden("Only the Registrar or Administrator can review enrollments.")
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "term"), pk=pk)
    decision = request.POST.get("decision")
    if enrollment.status != "PENDING":
        messages.error(request, "Only pending enrollments can be reviewed.")
        return redirect("enrollment_list")
    if decision == "approve":
        list(SubjectOffering.objects.select_for_update().filter(
            pk__in=enrollment.subjects.values_list("offering_id", flat=True)).order_by("pk"))
        errors = validate_enrollment(enrollment)
        missing = missing_required_documents(enrollment)
        if missing: errors.append("Required verified documents are missing: " + ", ".join(missing) + ".")
        if errors:
            for error in errors: messages.error(request, error)
        else:
            enrollment.status = "ENROLLED"; enrollment.approved_by = request.user
            enrollment.save(update_fields=["status", "approved_by"]); recalculate_assessment(enrollment); issue_cor(enrollment, request.user)
            AcademicRecord.objects.create(student=enrollment.student, term=enrollment.term, program=enrollment.student.program,
                year_level=enrollment.student.year_level, record_type="ENROLLMENT", status="ENROLLED",
                effective_date=timezone.localdate(), notes=f"Enrollment #{enrollment.pk} approved.", created_by=request.user)
            AuditLog.objects.create(user=request.user, action="Approved enrollment and issued COR", object_type="Enrollment", object_id=str(enrollment.pk))
            messages.success(request, "Enrollment approved and a COR version was issued.")
    elif decision == "reject":
        enrollment.status = "REJECTED"; enrollment.approved_by = request.user; enrollment.save(update_fields=["status", "approved_by"])
        AuditLog.objects.create(user=request.user, action="Rejected enrollment", object_type="Enrollment", object_id=str(enrollment.pk))
        messages.warning(request, "Enrollment rejected.")
    return redirect("enrollment_list")


@login_required
def enrollment_change_request(request, pk):
    denied = guard(request, "enrollment")
    if denied: return denied
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "term"), pk=pk)
    is_student = request.user.groups.filter(name="Student").exists()
    if is_student and enrollment.student.user_id != request.user.id:
        return HttpResponseForbidden("You can only request changes to your own enrollment.")
    if not (is_student or can_manage(request)):
        return HttpResponseForbidden("Only the student or Registrar may submit an add/drop request.")
    if enrollment.status not in ["APPROVED", "ENROLLED"]:
        messages.error(request, "Post-approval add/drop is available only after approval.")
        return redirect("student_enrollment_portal" if is_student else "enrollment_list")
    form = EnrollmentChangeRequestForm(request.POST or None)
    available_adds = SubjectOffering.objects.filter(section__term=enrollment.term, section__program=enrollment.student.program)
    current_drops = SubjectOffering.objects.filter(enrollmentsubject__enrollment=enrollment)
    form.fields["offering"].queryset = (available_adds | current_drops).distinct().select_related("curriculum_subject__subject", "section")
    if not add_drop_period_open(enrollment.term):
        messages.error(request, "The official add/drop period is currently closed.")
        return redirect("student_enrollment_portal" if is_student else "enrollment_list")
    if request.method == "POST" and form.is_valid():
        kind = form.cleaned_data["change_type"]
        offering = form.cleaned_data["offering"]
        if kind == "ADD" and not available_adds.filter(pk=offering.pk).exists():
            form.add_error("offering", "Choose an offering available in this term and program.")
        elif kind == "DROP" and not current_drops.filter(pk=offering.pk).exists():
            form.add_error("offering", "Choose a subject currently in this enrollment.")
        if form.errors:
            return render(request, "core/enrollment_change_form.html", {"form": form, "enrollment": enrollment})
        change = EnrollmentChange.objects.create(enrollment=enrollment, change_type=kind,
            subject_code=offering.curriculum_subject.subject.code,
            from_offering=offering if kind == "DROP" else None,
            to_offering=offering if kind == "ADD" else None,
            reason=form.cleaned_data["reason"], status="PENDING", changed_by=request.user)
        AuditLog.objects.create(user=request.user, action=f"Requested post-approval {kind.lower()}", object_type="EnrollmentChange", object_id=str(change.pk))
        messages.success(request, "Your request has been sent to the Registrar for review.")
        return redirect("student_enrollment_portal" if is_student else "enrollment_list")
    return render(request, "core/enrollment_change_form.html", {"form": form, "enrollment": enrollment})


@login_required
def enrollment_changes(request):
    denied = guard(request, "enrollment")
    if denied: return denied
    if not can_manage(request): return HttpResponseForbidden("Only the Registrar or Administrator can review add/drop requests.")
    changes = EnrollmentChange.objects.filter(status="PENDING").select_related("enrollment__student", "enrollment__term", "from_offering__curriculum_subject__subject", "to_offering__curriculum_subject__subject", "changed_by").order_by("created_at")
    return render(request, "core/enrollment_changes.html", {"changes": changes})


@login_required
@require_POST
def enrollment_change_review(request, pk):
    denied = guard(request, "enrollment")
    if denied: return denied
    if not can_manage(request): return HttpResponseForbidden("Only the Registrar or Administrator can review add/drop requests.")
    change = get_object_or_404(EnrollmentChange.objects.select_related("enrollment"), pk=pk)
    decision = request.POST.get("decision")
    if decision == "REJECTED":
        change.status = "REJECTED"; change.reviewed_by = request.user; change.reviewed_at = timezone.now()
        change.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        AuditLog.objects.create(user=request.user, action="Rejected enrollment change", object_type="EnrollmentChange", object_id=str(change.pk))
        messages.warning(request, "Add/drop request rejected.")
    elif decision == "APPROVED":
        from django.core.exceptions import ValidationError
        try:
            from .services import apply_approved_enrollment_change
            apply_approved_enrollment_change(change, request.user)
            messages.success(request, "Add/drop request approved, enrollment updated, and a revised COR issued where applicable.")
        except ValidationError as exc:
            messages.error(request, "Request could not be applied: " + "; ".join(exc.messages))
    else:
        return HttpResponseForbidden("Invalid decision.")
    return redirect("enrollment_changes")

@login_required
def cor_list(request, pk):
    denied = guard(request, "enrollment")
    if denied: return denied
    enrollment = get_object_or_404(Enrollment.objects.select_related("student", "term"), pk=pk)
    if request.user.groups.filter(name="Student").exists() and enrollment.student.user_id != request.user.id:
        return HttpResponseForbidden("You can only view your own Certificate of Registration.")
    if enrollment.status in ["APPROVED", "ENROLLED"] and not enrollment.cor_versions.exists():
        ensure_cor_for_enrolled(enrollment, request.user)
    return render(request, "core/cor_list.html", {"enrollment": enrollment, "versions": enrollment.cor_versions.all()})

@login_required
def cor_print(request, pk, version):
    denied = guard(request, "enrollment")
    if denied: return denied
    cor = get_object_or_404(CORVersion.objects.select_related("enrollment__student", "enrollment__term"), enrollment_id=pk, version=version)
    if request.user.groups.filter(name="Student").exists() and cor.enrollment.student.user_id != request.user.id:
        return HttpResponseForbidden("You can only view your own Certificate of Registration.")
    return render(request, "core/cor_print.html", {"cor": cor, "data": cor.snapshot})

@transaction.atomic
@login_required
@require_POST
def payment_verify(request, pk):
    denied = guard(request, "billing")
    if denied: return denied
    if not (request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()):
        return HttpResponseForbidden("Only the Cashier or Administrator can verify payments.")
    payment = get_object_or_404(Payment.objects.select_for_update().select_related("enrollment"), pk=pk)
    status = request.POST.get("status")
    if status not in ["VERIFIED", "REJECTED"]:
        return HttpResponseForbidden("Invalid payment verification status.")
    payment.verification_status = status
    payment.verified_by = request.user
    payment.verified_at = timezone.now()
    payment.rejection_reason = request.POST.get("rejection_reason", "").strip() if status == "REJECTED" else ""
    if status == "VERIFIED" and not payment.receipt_number:
        payment.receipt_number = f"OR-{timezone.localdate():%Y%m}-{payment.pk:06d}"
    payment.save(update_fields=["verification_status", "verified_by", "verified_at", "rejection_reason", "receipt_number"])
    revised_cor = None
    if payment.enrollment.status in ["APPROVED", "ENROLLED"]:
        revised_cor = refresh_cor_after_payment(payment.enrollment, status, actor=request.user)
    AuditLog.objects.create(user=request.user, action=f"Payment {status.lower()}", object_type="Payment", object_id=str(payment.pk))
    if revised_cor and revised_cor.reason.startswith("Payment verification updated"):
        AuditLog.objects.create(user=request.user, action=f"COR version {revised_cor.version} issued after payment {status.lower()}", object_type="CORVersion", object_id=str(revised_cor.pk))
    messages.success(request, f"Payment marked {status.lower()}." + (f" Receipt {payment.receipt_number} issued." if status == "VERIFIED" else ""))
    return redirect("billing_list")


@login_required
def payment_proof_download(request, pk):
    from django.http import FileResponse, Http404
    payment = get_object_or_404(Payment.objects.select_related("enrollment__student"), pk=pk)
    is_staff = request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()
    if not is_staff and payment.enrollment.student.user_id != request.user.id:
        return HttpResponseForbidden("You cannot access this payment proof.")
    if not payment.proof_file:
        raise Http404("No proof of payment was uploaded.")
    return FileResponse(payment.proof_file.open("rb"), as_attachment=True, filename=payment.proof_file.name.split("/")[-1])


@login_required
def payment_receipt(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("enrollment__student", "enrollment__term", "verified_by"), pk=pk)
    is_staff = request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()
    if not is_staff and payment.enrollment.student.user_id != request.user.id:
        return HttpResponseForbidden("You can only view your own receipt.")
    if payment.verification_status != "VERIFIED":
        return HttpResponseForbidden("A receipt is available only after payment verification.")
    return render(request, "core/payment_receipt.html", {"payment": payment})


@login_required
@require_POST
def financial_adjustment_review(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()):
        return HttpResponseForbidden("Only the Cashier or Administrator can review financial adjustments.")
    adjustment = get_object_or_404(FinancialAdjustment.objects.select_related("enrollment"), pk=pk)
    decision = request.POST.get("decision")
    if decision not in ("APPROVED", "REJECTED"):
        return HttpResponseForbidden("Invalid adjustment decision.")
    if decision == "APPROVED":
        totals = financial_totals(adjustment.enrollment)
        if adjustment.kind in ("SCHOLARSHIP", "WAIVER") and adjustment.amount > max(totals["gross_assessment"] - totals["scholarships"], Decimal("0.00")):
            messages.error(request, "Scholarship/waiver exceeds the remaining gross assessment.")
            return redirect("billing_list")
        if adjustment.kind == "REFUND" and adjustment.amount > max(sum((p.amount for p in adjustment.enrollment.payments.filter(verification_status="VERIFIED")), Decimal("0.00")) - totals["refunds"], Decimal("0.00")):
            messages.error(request, "Refund exceeds the net verified payments available to refund.")
            return redirect("billing_list")
    adjustment.status = decision
    adjustment.reviewed_by = request.user
    adjustment.reviewed_at = timezone.now()
    adjustment.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    if adjustment.enrollment.status in ["APPROVED", "ENROLLED"]:
        refresh_cor_after_payment(adjustment.enrollment, f"{adjustment.kind} {decision}", actor=request.user)
    AuditLog.objects.create(user=request.user, action=f"Financial adjustment {decision.lower()}", object_type="FinancialAdjustment", object_id=str(adjustment.pk))
    messages.success(request, f"Financial adjustment {decision.lower()}.")
    return redirect("billing_list")


@login_required
def financial_adjustment_create(request):
    if not (request.user.is_superuser or request.user.groups.filter(name__in=["Administrator", "Cashier"]).exists()):
        return HttpResponseForbidden("Only the Cashier or Administrator can create financial adjustments.")
    form = FinancialAdjustmentForm(request.POST or None)
    form.fields["enrollment"].queryset = Enrollment.objects.filter(status__in=["APPROVED", "ENROLLED"])
    if request.method == "POST" and form.is_valid():
        adjustment = form.save(commit=False)
        adjustment.created_by = request.user
        adjustment.save()
        AuditLog.objects.create(user=request.user, action="Created financial adjustment", object_type="FinancialAdjustment", object_id=str(adjustment.pk))
        messages.success(request, "Adjustment submitted for approval. It will affect the account only after approval.")
        return redirect("billing_list")
    return render(request, "core/form.html", {"form": form, "title": "Scholarship / Waiver / Charge / Refund", "cancel_url": reverse("billing_list")})


@login_required
def student_documents(request):
    denied = guard(request, "students")
    if denied: return denied
    student = Student.objects.filter(user=request.user).first()
    if not student and not can_manage(request): return HttpResponseForbidden("No student record is linked to this account.")
    if request.method == "POST":
        if not student: return HttpResponseForbidden("Staff should manage document records through Student Documents.")
        form = StudentDocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            incoming = form.save(commit=False)
            doc, created = StudentDocument.objects.get_or_create(student=student, term=incoming.term, document_type=incoming.document_type,
                defaults={"notes": incoming.notes, "file": incoming.file, "status": "SUBMITTED"})
            if not created:
                doc.notes = incoming.notes; doc.file = incoming.file; doc.status = "SUBMITTED"; doc.reviewed_by = None; doc.save()
            AuditLog.objects.create(user=request.user, action="Submitted student document", object_type="StudentDocument", object_id=str(doc.pk))
            messages.success(request, "Document submitted for Registrar verification."); return redirect("student_documents")
    else:
        form = StudentDocumentUploadForm()
        if student: form.fields["term"].queryset = SchoolTerm.objects.all()
    docs = StudentDocument.objects.select_related("student", "term")
    if student: docs = docs.filter(student=student)
    return render(request, "core/student_documents.html", {"form": form, "documents": docs.order_by("-updated_at"), "is_student": bool(student)})

@login_required
def student_document_download(request, pk):
    from django.http import FileResponse, Http404
    doc = get_object_or_404(StudentDocument.objects.select_related("student"), pk=pk)
    if not (request.user.is_superuser or can_manage(request) or doc.student.user_id == request.user.id):
        return HttpResponseForbidden("You cannot access this document.")
    if not doc.file: raise Http404("No file was uploaded for this document.")
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.file.name.split("/")[-1])

from django.contrib.auth.views import PasswordChangeView


@login_required
@require_POST
def student_send_password_reset(request, pk):
    """Send a single-use password reset link to a student's registered email."""
    if not can_manage(request):
        return HttpResponseForbidden("Only the Registrar or Administrator can send student password reset links.")
    student = get_object_or_404(Student.objects.select_related("user"), pk=pk)
    if not student.user_id:
        messages.error(request, "This student does not have a linked portal account.")
        return redirect("student_detail", pk=student.pk)

    # Keep the portal account's reset destination aligned with the student record.
    if student.email and student.user.email != student.email:
        student.user.email = student.email
        student.user.save(update_fields=["email"])

    if not student.user.email:
        messages.error(request, "No email address is registered for this student. Update the student's email before sending a reset link.")
        return redirect("student_detail", pk=student.pk)

    form = PasswordResetForm({"email": student.user.email})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            email_template_name="registration/password_reset_email.txt",
            subject_template_name="registration/password_reset_subject.txt",
            html_email_template_name="registration/password_reset_email.html",
        )
        messages.success(request, f"A password reset link was sent to {student.user.email}.")
    else:
        messages.error(request, "A reset link could not be generated. Check the student's registered email address.")
    return redirect("student_detail", pk=student.pk)


class StudentPasswordChangeView(PasswordChangeView):
    def form_valid(self, form):
        response = super().form_valid(form)
        Student.objects.filter(user=self.request.user).update(must_change_password=False)
        return response
