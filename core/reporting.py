"""Twelve operational and financial report datasets used by the Reports page."""
from decimal import Decimal
from .models import (Student, Enrollment, EnrollmentSubject, SubjectOffering, Grade,
                     Payment, AcademicRecord)
from .services import financial_totals

REPORTS = [
    ("enrollments", "Enrollment summary"),
    ("students", "Student masterlist"),
    ("admissions", "Admission and student standing"),
    ("enrollment_status", "Enrollment status by term"),
    ("class_rosters", "Class / section rosters"),
    ("capacity", "Subject offering capacity"),
    ("grade_distribution", "Grade distribution"),
    ("academic_performance", "Student academic performance"),
    ("assessment_ledger", "Assessment and scholarship ledger"),
    ("payment_collections", "Payment collections"),
    ("outstanding_balances", "Outstanding student balances"),
    ("financial_reconciliation", "Financial reconciliation"),
]


def build_report(report_type, term_id=None, program_id=None, status=None):
    headers, rows = [], []
    enrollments = Enrollment.objects.select_related("student__program__department", "term").prefetch_related("assessment_items", "payments", "financial_adjustments")
    if term_id:
        enrollments = enrollments.filter(term_id=term_id)
    if program_id:
        enrollments = enrollments.filter(student__program_id=program_id)
    if status:
        enrollments = enrollments.filter(status=status)

    if report_type == "enrollments":
        headers = ["Student ID", "Student", "College", "Program", "Year", "Term", "Status"]
        rows = [[e.student.student_id, str(e.student), e.student.program.department.name, e.student.program.code, e.student.year_level, str(e.term), e.get_status_display()] for e in enrollments.order_by("term__school_year", "student__student_id")]
    elif report_type == "students":
        qs = Student.objects.select_related("program__department").order_by("student_id")
        if program_id: qs = qs.filter(program_id=program_id)
        headers = ["Student ID", "Student", "College", "Program", "Year", "Admission category", "Standing", "Account status", "Email", "Phone"]
        rows = [[s.student_id, str(s), s.program.department.name, s.program.code, s.year_level, s.get_admission_category_display(), s.get_enrollment_standing_display(), s.get_account_status_display(), s.email, s.phone] for s in qs]
    elif report_type == "admissions":
        qs = AcademicRecord.objects.filter(record_type="ADMISSION").select_related("student", "program")
        if program_id: qs = qs.filter(student__program_id=program_id)
        if term_id: qs = qs.filter(term_id=term_id)
        headers = ["Student ID", "Student", "Program", "Admission record", "Status", "Effective date", "Notes"]
        rows = [[r.student.student_id, str(r.student), r.program.code if r.program else "", r.get_record_type_display(), r.status, r.effective_date or "", r.notes] for r in qs]
    elif report_type == "enrollment_status":
        headers = ["Term", "Status", "Enrollment count"]
        from django.db.models import Count
        groups = enrollments.values("term__name", "term__school_year", "status").annotate(total=Count("id")).order_by("term__school_year", "term__name", "status")
        rows = [[f"{g['term__name']} AY {g['term__school_year']}", g["status"], g["total"]] for g in groups]
    elif report_type == "class_rosters":
        qs = EnrollmentSubject.objects.filter(enrollment__in=enrollments).select_related("enrollment__student", "enrollment__term", "offering__section", "offering__curriculum_subject__subject", "offering__instructor__user")
        headers = ["Term", "Subject code", "Subject", "Section", "Instructor", "Student ID", "Student", "Enrollment status"]
        rows = [[str(x.enrollment.term), x.offering.curriculum_subject.subject.code, x.offering.curriculum_subject.subject.title, x.offering.section.code, str(x.offering.instructor), x.enrollment.student.student_id, str(x.enrollment.student), x.enrollment.status] for x in qs.order_by("enrollment__term__school_year", "offering__section__code", "enrollment__student__student_id")]
    elif report_type == "capacity":
        qs = SubjectOffering.objects.select_related("section__term", "section__program", "curriculum_subject__subject", "instructor__user")
        if term_id: qs = qs.filter(section__term_id=term_id)
        if program_id: qs = qs.filter(section__program_id=program_id)
        headers = ["Term", "Program", "Subject", "Section", "Instructor", "Capacity", "Reserved seats", "Available seats"]
        for o in qs:
            used = EnrollmentSubject.objects.filter(offering=o, enrollment__status__in=["APPROVED", "ENROLLED"]).count()
            rows.append([str(o.section.term), o.section.program.code, o.curriculum_subject.subject.code, o.section.code, str(o.instructor), o.capacity, used, max(o.capacity-used, 0)])
    elif report_type == "grade_distribution":
        qs = Grade.objects.filter(enrollment_subject__enrollment__in=enrollments).select_related("enrollment_subject__offering__curriculum_subject__subject")
        headers = ["Subject", "Final grade", "Count"]
        counts = {}
        for g in qs:
            key = (g.enrollment_subject.offering.curriculum_subject.subject.code, str(g.final) if g.final is not None else "Not encoded")
            counts[key] = counts.get(key, 0) + 1
        rows = [[a, b, c] for (a, b), c in sorted(counts.items())]
    elif report_type == "academic_performance":
        qs = Grade.objects.filter(enrollment_subject__enrollment__in=enrollments).select_related("enrollment_subject__enrollment__student", "enrollment_subject__enrollment__term", "enrollment_subject__offering__curriculum_subject__subject")
        headers = ["Student ID", "Student", "Term", "Subject", "Prelim", "Midterm", "Final", "Remarks"]
        rows = [[g.enrollment_subject.enrollment.student.student_id, str(g.enrollment_subject.enrollment.student), str(g.enrollment_subject.enrollment.term), g.enrollment_subject.offering.curriculum_subject.subject.code, g.prelim or "", g.midterm or "", g.final or "", g.remarks] for g in qs]
    elif report_type == "assessment_ledger":
        headers = ["Student ID", "Student", "Term", "Gross assessment", "Scholarship / waiver", "Additional charges", "Net assessment"]
        for e in enrollments:
            t = financial_totals(e)
            rows.append([e.student.student_id, str(e.student), str(e.term), t["gross_assessment"], t["scholarships"], t["additional_charges"], t["assessment"]])
    elif report_type == "payment_collections":
        qs = Payment.objects.filter(enrollment__in=enrollments, verification_status="VERIFIED").select_related("enrollment__student", "enrollment__term", "verified_by").order_by("verified_at")
        headers = ["Receipt number", "Student ID", "Student", "Term", "Method", "Reference", "Amount", "Verified at", "Verified by"]
        rows = [[p.receipt_number or "", p.enrollment.student.student_id, str(p.enrollment.student), str(p.enrollment.term), p.get_method_display(), p.reference_no, p.amount, p.verified_at or "", str(p.verified_by or "")] for p in qs]
    elif report_type == "outstanding_balances":
        headers = ["Student ID", "Student", "Term", "Assessment", "Verified paid", "Balance", "Payment status"]
        for e in enrollments:
            t = financial_totals(e)
            if t["balance"] > 0:
                rows.append([e.student.student_id, str(e.student), str(e.term), t["assessment"], t["verified_payments"], t["balance"], t["payment_status"]])
    elif report_type == "financial_reconciliation":
        headers = ["Student ID", "Student", "Term", "Gross assessment", "Scholarship / waiver", "Charges", "Net assessment", "Verified payments", "Refunds", "Net paid", "Balance"]
        for e in enrollments:
            t = financial_totals(e)
            rows.append([e.student.student_id, str(e.student), str(e.term), t["gross_assessment"], t["scholarships"], t["additional_charges"], t["assessment"], sum((p.amount for p in e.payments.filter(verification_status="VERIFIED")), Decimal("0.00")), t["refunds"], t["verified_payments"], t["balance"]])
    else:
        report_type = "enrollments"
        return build_report(report_type, term_id, program_id, status)
    return headers, rows
