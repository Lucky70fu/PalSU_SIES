"""Transactional enrollment, prerequisite, assessment and COR services."""
from decimal import Decimal
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.utils import timezone
from .models import (AssessmentItem, AssessmentVersion, AuditLog, CORVersion, CurriculumSubject,
    Enrollment, EnrollmentChange, EnrollmentSubject, Fee, Grade, SchoolTerm, StudentDocument, SubjectOffering, FinancialAdjustment, Payment)

DOCUMENT_REQUIREMENTS = {
    "REGULAR": ["Grade Card", "Pre-Enrollment Form", "Clearance"],
    "IRREGULAR": ["Grade Card", "Pre-Enrollment Form", "Clearance"],
    "LATE": ["Grade Card", "Pre-Enrollment Form", "Clearance"],
    "FRESHMAN": ["Medical Certificate", "Good Moral Certificate", "PSA/Birth Certificate", "SF9/Form 138", "ID Picture", "Notice of Admission"],
    "SHIFTY": ["Shifting Form", "Previous Clearance"],
    "TRANSFEREE": ["Transcript of Records", "Medical Certificate", "Good Moral Certificate", "PSA/Birth Certificate", "ID Picture", "Admission Form", "Certificate of Transfer"],
    "RETURNING": ["Readmission Form", "Guidance Office document"],
}

def enrollment_period_open(term, now=None):
    now = now or timezone.now()
    return bool(term.is_open and (not term.enrollment_opens or now >= term.enrollment_opens)
                and (not term.enrollment_closes or now <= term.enrollment_closes))

def add_drop_period_open(term, now=None):
    now = now or timezone.now()
    return bool(term.add_drop_opens and term.add_drop_closes and term.add_drop_opens <= now <= term.add_drop_closes)

def completed_subject_ids(student, term):
    return set(Grade.objects.filter(
        enrollment_subject__enrollment__student=student,
        enrollment_subject__enrollment__status__in=["APPROVED", "ENROLLED"],
        final__isnull=False, final__lte=term.passing_grade,
    ).values_list("enrollment_subject__offering__curriculum_subject__subject_id", flat=True))

def _offering_has_seat(offering, excluding_enrollment=None):
    qs = EnrollmentSubject.objects.filter(offering=offering, enrollment__status__in=["APPROVED", "ENROLLED"])
    if excluding_enrollment:
        qs = qs.exclude(enrollment=excluding_enrollment)
    return qs.count() < offering.capacity

@transaction.atomic
def lock_and_check_offering_capacity(offering_id, excluding_enrollment=None):
    """Serialize seat claims on databases supporting SELECT FOR UPDATE (e.g. MySQL)."""
    offering = SubjectOffering.objects.select_for_update().get(pk=offering_id)
    return _offering_has_seat(offering, excluding_enrollment=excluding_enrollment)


def _offering_conflicts(offering, selected_offerings):
    candidate = list(offering.schedules.all())
    existing = [s for selected in selected_offerings for s in selected.schedules.all()]
    return any(a.day == b.day and a.start_time < b.end_time and a.end_time > b.start_time
               for a in candidate for b in existing)

def generate_initial_subjects(student, term):
    """Build a prerequisite-safe list from the current curriculum and official offerings."""
    offerings = list(SubjectOffering.objects.filter(
        section__term=term, section__program=student.program,
        section__year_level=F("curriculum_subject__year_level"),
        curriculum_subject__program=student.program,
    ).select_related("curriculum_subject__subject", "section", "instructor").prefetch_related(
        "schedules", "curriculum_subject__prerequisites"
    ).order_by("curriculum_subject__subject__code", "section__code"))
    by_subject = {}
    for offering in offerings:
        by_subject.setdefault(offering.curriculum_subject.subject_id, []).append(offering)
    completed = completed_subject_ids(student, term)
    selected, selected_ids, explanations, warnings = [], set(), [], []

    def choose(subject_id, chain=()):
        if subject_id in completed or subject_id in selected_ids:
            return True
        if subject_id in chain:
            warnings.append("Circular prerequisite detected in curriculum configuration.")
            return False
        for option in by_subject.get(subject_id, []):
            if not _offering_has_seat(option) or _offering_conflicts(option, selected):
                continue
            prerequisites_ok = True
            for prereq in option.curriculum_subject.prerequisites.all():
                if not choose(prereq.pk, chain + (subject_id,)):
                    prerequisites_ok = False
            if not prerequisites_ok:
                continue
            selected.append(option)
            selected_ids.add(subject_id)
            return True
        return False

    requirements = CurriculumSubject.objects.filter(
        program=student.program, year_level=student.year_level, semester=term.name
    ).select_related("subject").order_by("subject__code")
    for curriculum in requirements:
        if curriculum.subject_id in completed:
            continue
        missing = [p for p in curriculum.prerequisites.all() if p.pk not in completed]
        if missing:
            for prereq in missing:
                if choose(prereq.pk):
                    explanations.append(f"{curriculum.subject.code} is deferred because {prereq.code} has not yet been completed; {prereq.code} was added where offered.")
                else:
                    warnings.append(f"{curriculum.subject.code} cannot be proposed: prerequisite {prereq.code} is incomplete and has no eligible available offering.")
            continue
        if not choose(curriculum.subject_id):
            warnings.append(f"{curriculum.subject.code} was not assigned because no eligible offering with capacity and a conflict-free schedule was found.")
    return selected, explanations, warnings

@transaction.atomic
def save_initial_subjects(enrollment, actor):
    selected, explanations, warnings = generate_initial_subjects(enrollment.student, enrollment.term)
    enrollment.subjects.all().delete()
    for offering in selected:
        EnrollmentSubject.objects.create(enrollment=enrollment, offering=offering)
        EnrollmentChange.objects.create(enrollment=enrollment, change_type="SYSTEM",
            subject_code=offering.curriculum_subject.subject.code, to_offering=offering,
            reason="Automatic curriculum assignment", changed_by=actor)
    for explanation in explanations:
        AuditLog.objects.create(user=actor, action=("Prerequisite replacement: " + explanation)[:150], object_type="Enrollment", object_id=str(enrollment.pk))
    for warning in warnings:
        AuditLog.objects.create(user=actor, action=("Prerequisite warning: " + warning)[:150], object_type="Enrollment", object_id=str(enrollment.pk))
    return explanations, warnings

def missing_required_documents(enrollment):
    required = DOCUMENT_REQUIREMENTS.get(enrollment.enrollment_type, [])
    verified = set(StudentDocument.objects.filter(student=enrollment.student, term=enrollment.term, status="VERIFIED").values_list("document_type", flat=True))
    return [name for name in required if name not in verified]

def validate_enrollment(enrollment):
    errors = []
    active = list(enrollment.subjects.select_related("offering__curriculum_subject__subject", "offering__section").prefetch_related("offering__schedules", "offering__curriculum_subject__prerequisites"))
    if not active:
        errors.append("Select at least one subject before submitting enrollment.")
    total_units = sum((x.offering.curriculum_subject.subject.units for x in active), Decimal("0"))
    if total_units < enrollment.term.minimum_units:
        errors.append(f"Selected units are below the minimum of {enrollment.term.minimum_units}.")
    if total_units > enrollment.term.maximum_units:
        errors.append(f"Selected units exceed the maximum of {enrollment.term.maximum_units}.")
    all_selected_ids = {x.offering.curriculum_subject.subject_id for x in active}
    seen, selected_offerings = set(), []
    completed = completed_subject_ids(enrollment.student, enrollment.term)
    for item in active:
        offering, subject = item.offering, item.offering.curriculum_subject.subject
        if subject.pk in seen: errors.append(f"Duplicate subject selected: {subject.code}.")
        seen.add(subject.pk)
        if (offering.section.term_id != enrollment.term_id or offering.section.program_id != enrollment.student.program_id
                or offering.curriculum_subject.program_id != enrollment.student.program_id
                or offering.curriculum_subject.year_level > enrollment.student.year_level
                or offering.section.year_level != offering.curriculum_subject.year_level):
            errors.append(f"{subject.code} is not eligible for this student's program, year level and term.")
        if not _offering_has_seat(offering, excluding_enrollment=enrollment): errors.append(f"{subject.code} / {offering.section.code} is full.")
        missing = [p.code for p in offering.curriculum_subject.prerequisites.all() if p.pk not in completed and p.pk not in all_selected_ids]
        if missing: errors.append(f"{subject.code} requires completed prerequisite(s): {', '.join(missing)}.")
        if _offering_conflicts(offering, selected_offerings): errors.append(f"{subject.code} has a schedule conflict.")
        selected_offerings.append(offering)
    return errors

@transaction.atomic
def recalculate_assessment(enrollment):
    previous = list(enrollment.assessment_items.values("description", "amount"))
    enrollment.assessment_items.all().delete()
    units = sum((x.offering.curriculum_subject.subject.units for x in enrollment.subjects.select_related("offering__curriculum_subject__subject")), Decimal("0"))
    fees = Fee.objects.filter(active=True).filter(Q(program__isnull=True) | Q(program=enrollment.student.program))
    fees = fees.filter(Q(term__isnull=True) | Q(term=enrollment.term))
    fees = fees.filter(Q(year_level__isnull=True) | Q(year_level=enrollment.student.year_level))
    for fee in fees:
        amount = fee.amount * units if fee.is_per_unit else fee.amount
        AssessmentItem.objects.create(enrollment=enrollment, fee=fee, description=fee.name, amount=amount.quantize(Decimal("0.01")))
    current = list(enrollment.assessment_items.values("description", "amount"))
    total = sum((x.amount for x in enrollment.assessment_items.all()), Decimal("0"))
    if current != previous:
        version = (enrollment.assessment_versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        AssessmentVersion.objects.create(enrollment=enrollment, version=version,
            snapshot={"items": [{"description": x["description"], "amount": str(x["amount"])} for x in current]}, total=total)
    return total

def financial_totals(enrollment):
    """Return the authoritative assessed, paid, refunded and balance totals."""
    gross = sum((x.amount for x in enrollment.assessment_items.all()), Decimal("0.00"))
    adjustments = list(enrollment.financial_adjustments.filter(status="APPROVED"))
    scholarships = sum((x.amount for x in adjustments if x.kind in ("SCHOLARSHIP", "WAIVER")), Decimal("0.00"))
    charges = sum((x.amount for x in adjustments if x.kind == "CHARGE"), Decimal("0.00"))
    refunds = sum((x.amount for x in adjustments if x.kind == "REFUND"), Decimal("0.00"))
    assessed = max(gross - scholarships + charges, Decimal("0.00"))
    verified_gross = sum((p.amount for p in enrollment.payments.filter(verification_status="VERIFIED")), Decimal("0.00"))
    verified = max(verified_gross - refunds, Decimal("0.00"))
    balance = max(assessed - verified, Decimal("0.00"))
    return {"gross_assessment": gross, "scholarships": scholarships, "additional_charges": charges,
            "refunds": refunds, "assessment": assessed, "verified_payments": verified,
            "balance": balance, "payment_status": "PAID" if assessed > 0 and balance <= 0 else ("PARTIALLY_PAID" if verified > 0 else "UNPAID")}


def cor_snapshot(enrollment):
    items = []
    for row in enrollment.subjects.select_related("offering__curriculum_subject__subject", "offering__section", "offering__instructor__user").prefetch_related("offering__schedules__room"):
        offering = row.offering
        items.append({"code": offering.curriculum_subject.subject.code, "title": offering.curriculum_subject.subject.title,
            "units": str(offering.curriculum_subject.subject.units), "section": offering.section.code,
            "instructor": str(offering.instructor), "schedules": [{"day": s.get_day_display(), "start": str(s.start_time), "end": str(s.end_time), "room": s.room.code} for s in offering.schedules.all()]})
    totals = financial_totals(enrollment)
    return {"student_id": enrollment.student.student_id, "student": str(enrollment.student), "program": str(enrollment.student.program),
        "term": str(enrollment.term), "subjects": items,
        "total_units": str(sum((Decimal(x["units"]) for x in items), Decimal("0"))),
        "gross_assessment": str(totals["gross_assessment"]), "scholarships": str(totals["scholarships"]),
        "additional_charges": str(totals["additional_charges"]), "refunds": str(totals["refunds"]),
        "assessment": str(totals["assessment"]), "verified_payments": str(totals["verified_payments"]),
        "balance": str(totals["balance"]), "payment_status": totals["payment_status"]}

@transaction.atomic
def issue_cor(enrollment, actor, reason="Initial approval"):
    version = (enrollment.cor_versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
    return CORVersion.objects.create(enrollment=enrollment, version=version, snapshot=cor_snapshot(enrollment), reason=reason, issued_by=actor)


def _cor_issuer(enrollment, actor=None):
    """Choose an authorized staff issuer; never attribute a COR to a student."""
    if enrollment.approved_by_id:
        return enrollment.approved_by
    if actor and (actor.is_superuser or actor.is_staff or actor.groups.filter(name__in=["Administrator", "Registrar"]).exists()):
        return actor
    User = get_user_model()
    return (User.objects.filter(is_superuser=True).order_by("id").first()
            or User.objects.filter(groups__name__in=["Administrator", "Registrar"]).order_by("id").first()
            or User.objects.filter(is_staff=True).order_by("id").first())


@transaction.atomic
def refresh_cor_after_payment(enrollment, payment_status, actor=None):
    """Issue a revised COR only when a payment status changes its financial snapshot.

    The prior COR version is retained for the audit trail. Repeated verification
    requests with no snapshot change do not create duplicate COR versions.
    """
    locked = (Enrollment.objects.select_for_update()
              .select_related("student", "term", "approved_by")
              .get(pk=enrollment.pk))
    if locked.status not in ["APPROVED", "ENROLLED"]:
        return None

    latest = locked.cor_versions.order_by("-version").first()
    current_snapshot = cor_snapshot(locked)
    if latest and latest.snapshot == current_snapshot:
        return latest

    if latest:
        # Preserve the Registrar/Administrator who issued the original COR.
        issuer = latest.issued_by
    else:
        issuer = _cor_issuer(locked, actor)
    if issuer is None:
        return None

    reason = f"Payment verification updated: {payment_status}"
    return issue_cor(locked, issuer, reason=reason)


@transaction.atomic
def ensure_cor_for_enrolled(enrollment, actor=None):
    """Create the initial COR for a legacy ENROLLED record if it is missing.

    This is safe to call repeatedly: an existing COR is returned unchanged, and
    records that are not ENROLLED are never issued a COR.
    """
    locked = Enrollment.objects.select_for_update().select_related("student", "term", "approved_by").get(pk=enrollment.pk)
    existing = locked.cor_versions.order_by("-version").first()
    if existing:
        return existing
    if locked.status not in ["APPROVED", "ENROLLED"]:
        return None
    issuer = _cor_issuer(locked, actor)
    if issuer is None:
        return None
    return issue_cor(locked, issuer, reason="Backfilled for previously approved enrollment")


@transaction.atomic
def apply_approved_enrollment_change(change, actor):
    """Apply a Registrar-approved post-approval add/drop and issue a revised COR."""
    from django.core.exceptions import ValidationError
    locked = Enrollment.objects.select_for_update().select_related("student", "term").get(pk=change.enrollment_id)
    change = EnrollmentChange.objects.select_for_update().select_related("from_offering", "to_offering").get(pk=change.pk)
    if change.status != "PENDING":
        raise ValidationError("This request has already been reviewed.")
    if locked.status not in ["APPROVED", "ENROLLED"]:
        raise ValidationError("Only approved/enrolled records can use the post-approval add/drop workflow.")
    if not add_drop_period_open(locked.term):
        raise ValidationError("The official add/drop period is closed.")
    if change.change_type == "ADD":
        offering = SubjectOffering.objects.select_for_update().select_related("curriculum_subject__subject", "section").get(pk=change.to_offering_id)
        if not _offering_has_seat(offering, excluding_enrollment=locked):
            raise ValidationError("The selected offering has no remaining seats.")
        if locked.subjects.filter(offering__curriculum_subject__subject_id=offering.curriculum_subject.subject_id).exists():
            raise ValidationError("The student is already enrolled in this subject.")
        EnrollmentSubject.objects.create(enrollment=locked, offering=offering)
    elif change.change_type == "DROP":
        item = locked.subjects.filter(offering_id=change.from_offering_id).first()
        if not item:
            raise ValidationError("The subject is no longer part of this enrollment.")
        item.delete()
    else:
        raise ValidationError("Unsupported post-approval change type.")
    errors = validate_enrollment(locked)
    if errors:
        raise ValidationError(errors)
    change.status = "APPROVED"
    change.reviewed_by = actor
    change.reviewed_at = timezone.now()
    change.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    recalculate_assessment(locked)
    latest = locked.cor_versions.order_by("-version").first()
    if latest:
        issue_cor(locked, latest.issued_by, reason=f"Registrar-approved {change.change_type.lower()} request #{change.pk}")
    AuditLog.objects.create(user=actor, action=f"Approved enrollment {change.change_type.lower()} request", object_type="EnrollmentChange", object_id=str(change.pk))
    return change
