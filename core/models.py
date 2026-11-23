from decimal import Decimal
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from .validators import validate_document_upload

class Department(models.Model):
    code = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=120)
    class Meta:
        verbose_name = "College"
        verbose_name_plural = "Colleges"
    def __str__(self): return self.name

class Program(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programs", verbose_name="College")
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    years_to_complete = models.PositiveSmallIntegerField(default=4)
    def __str__(self): return f"{self.code} - {self.name}"
    class Meta:
        verbose_name = "Academic Program"
        verbose_name_plural = "Academic Programs"

class Student(models.Model):
    GENDER = [("F","Female"),("M","Male"),("X","Prefer not to say")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    student_id = models.CharField(max_length=20, unique=True, blank=True)
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="students")
    year_level = models.PositiveSmallIntegerField(default=1)
    admission_category = models.CharField(max_length=20, default="REGULAR", choices=[("FRESHMAN","Freshman"),("TRANSFEREE","Transferee"),("RETURNING","Returning"),("SHIFTY","Shifty"),("REGULAR","Continuing Student")])
    enrollment_standing = models.CharField(max_length=20, default="REGULAR", choices=[("REGULAR","Regular"),("IRREGULAR","Irregular"),("PROBATIONARY","Probationary")])
    account_status = models.CharField(max_length=12, default="ACTIVE", choices=[("ACTIVE","Active"),("INACTIVE","Inactive"),("GRADUATED","Graduated")])
    must_change_password = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        if not self.student_id:
            super().save(*args, **kwargs)
            self.student_id = f"STU-{self.pk:06d}"
            return super().save(update_fields=["student_id"])
        return super().save(*args, **kwargs)
    def __str__(self): return f"{self.student_id} - {self.last_name}, {self.first_name}"

class SchoolTerm(models.Model):
    name = models.CharField(max_length=30)  # e.g. 1st Semester
    school_year = models.CharField(max_length=20)  # e.g. 2026-2027
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    is_open = models.BooleanField(default=False)
    enrollment_opens = models.DateTimeField(null=True, blank=True)
    enrollment_closes = models.DateTimeField(null=True, blank=True)
    add_drop_opens = models.DateTimeField(null=True, blank=True)
    add_drop_closes = models.DateTimeField(null=True, blank=True)
    passing_grade = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("3.00"))
    minimum_units = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("0.0"))
    maximum_units = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("30.0"))
    class Meta:
        constraints = [models.UniqueConstraint(fields=["name","school_year"], name="unique_school_term")]
    def __str__(self): return f"{self.name} AY {self.school_year}"

class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=160)
    units = models.DecimalField(max_digits=4, decimal_places=1, validators=[MinValueValidator(Decimal("0.5"))])
    description = models.TextField(blank=True)
    def __str__(self): return f"{self.code} - {self.title}"

class CurriculumSubject(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    year_level = models.PositiveSmallIntegerField()
    semester = models.CharField(max_length=20)
    prerequisites = models.ManyToManyField(Subject, blank=True, related_name="required_for")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["program","subject","year_level","semester"], name="unique_curriculum_subject")]
    def __str__(self): return f"{self.program.code}: {self.subject.code}"

class Instructor(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    employee_no = models.CharField(max_length=30, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, verbose_name="College")
    def __str__(self): return self.user.get_full_name() or self.user.username

class Room(models.Model):
    code = models.CharField(max_length=30, unique=True)
    capacity = models.PositiveIntegerField(default=40)
    def __str__(self): return self.code

class Section(models.Model):
    code = models.CharField(max_length=30)
    term = models.ForeignKey(SchoolTerm, on_delete=models.PROTECT)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    year_level = models.PositiveSmallIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=["code","term"], name="unique_section_term")]
    def __str__(self): return self.code

class SubjectOffering(models.Model):
    curriculum_subject = models.ForeignKey(CurriculumSubject, on_delete=models.PROTECT)
    section = models.ForeignKey(Section, on_delete=models.PROTECT)
    instructor = models.ForeignKey(Instructor, on_delete=models.PROTECT)
    capacity = models.PositiveIntegerField(default=40)
    def __str__(self): return f"{self.curriculum_subject.subject.code} / {self.section}"

class ClassSchedule(models.Model):
    DAYS = [(str(i), d) for i,d in enumerate(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"])]
    offering = models.ForeignKey(SubjectOffering, on_delete=models.CASCADE, related_name="schedules")
    day = models.CharField(max_length=1, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(Room, on_delete=models.PROTECT)
    def clean(self):
        from django.core.exceptions import ValidationError
        from django.db.models import Q
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be later than start time.")
        clashes = ClassSchedule.objects.filter(
            day=self.day, start_time__lt=self.end_time, end_time__gt=self.start_time,
            offering__section__term_id=self.offering.section.term_id,
        )
        if self.pk: clashes = clashes.exclude(pk=self.pk)
        clashes = clashes.filter(Q(room=self.room) | Q(offering__instructor=self.offering.instructor))
        if clashes.exists():
            raise ValidationError("Schedule conflict: room or instructor is already booked.")
    def save(self, *args, **kwargs):
        from django.db import transaction
        with transaction.atomic():
            if self.room_id:
                Room.objects.select_for_update().get(pk=self.room_id)
            if self.offering_id:
                offering = SubjectOffering.objects.select_for_update().get(pk=self.offering_id)
                Instructor.objects.select_for_update().get(pk=offering.instructor_id)
            self.full_clean()
            return super().save(*args, **kwargs)
    def __str__(self): return f"{self.get_day_display()} {self.start_time}-{self.end_time}"

class Enrollment(models.Model):
    STATUS = [("PENDING","Pending"),("APPROVED","Approved"),("ENROLLED","Enrolled"),("REJECTED","Rejected")]
    TYPE = [("FRESHMAN","Freshman"),("REGULAR","Regular"),("IRREGULAR","Irregular"),("LATE","Late"),("TRANSFEREE","Transferee"),("SHIFTY","Shifty"),("RETURNING","Returning")]
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    term = models.ForeignKey(SchoolTerm, on_delete=models.PROTECT)
    enrollment_type = models.CharField(max_length=15, choices=TYPE, default="REGULAR")
    status = models.CharField(max_length=10, choices=STATUS, default="PENDING")
    submitted_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["student","term"], name="one_enrollment_per_student_term")]
    def __str__(self): return f"{self.student} / {self.term}"

class EnrollmentSubject(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="subjects")
    offering = models.ForeignKey(SubjectOffering, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["enrollment","offering"], name="unique_enrollment_offering")]

class Fee(models.Model):
    CATEGORIES = [("TUITION", "Tuition"), ("MISC", "Miscellaneous"), ("LAB", "Laboratory"), ("LIBRARY", "Library"), ("OTHER", "Other")]
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=12, choices=CATEGORIES, default="OTHER")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    is_per_unit = models.BooleanField(default=False)
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank to apply to all programs.")
    term = models.ForeignKey(SchoolTerm, on_delete=models.SET_NULL, null=True, blank=True, help_text="Leave blank to apply to all terms.")
    year_level = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Leave blank to apply to all year levels.")
    active = models.BooleanField(default=True)
    def __str__(self): return self.name

class AssessmentItem(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="assessment_items")
    fee = models.ForeignKey(Fee, on_delete=models.PROTECT)
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    class Meta: ordering = ["id"]

class Payment(models.Model):
    VERIFICATION = [("PENDING","Pending"),("VERIFIED","Verified"),("REJECTED","Rejected")]
    METHOD = [("CASH","Cash"),("GCASH","GCash"),("MAYA","Maya"),("BANK","Bank Transfer"),("OTHER","Other")]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=10, choices=METHOD)
    reference_no = models.CharField(max_length=100, blank=True)
    verification_status = models.CharField(max_length=10, choices=VERIFICATION, default="PENDING")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_payments")
    verified_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    proof_file = models.FileField(upload_to="payment_proofs/%Y/%m/", blank=True, null=True, validators=[validate_document_upload])
    receipt_number = models.CharField(max_length=40, blank=True, unique=True, null=True)
    rejection_reason = models.TextField(blank=True)
    paid_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Payment #{self.pk} - {self.amount}"

class Grade(models.Model):
    enrollment_subject = models.OneToOneField(EnrollmentSubject, on_delete=models.CASCADE)
    prelim = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    midterm = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    final = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    remarks = models.CharField(max_length=30, blank=True)

class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=150)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class StudentDocument(models.Model):
    STATUS = [("PENDING","Pending"),("SUBMITTED","Submitted"),("VERIFIED","Verified"),("REJECTED","Rejected")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="documents")
    term = models.ForeignKey(SchoolTerm, on_delete=models.PROTECT, null=True, blank=True)
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to="student_documents/%Y/%m/", validators=[validate_document_upload], null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="PENDING")
    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["student","term","document_type"], name="unique_student_term_document")]

class EnrollmentChange(models.Model):
    CHANGE_TYPES = [("ADD","Add"),("DROP","Drop"),("SECTION","Section Change"),("SYSTEM","System Assignment")]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="changes")
    change_type = models.CharField(max_length=10, choices=CHANGE_TYPES)
    subject_code = models.CharField(max_length=20)
    from_offering = models.ForeignKey(SubjectOffering, on_delete=models.PROTECT, null=True, blank=True, related_name="changes_from")
    to_offering = models.ForeignKey(SubjectOffering, on_delete=models.PROTECT, null=True, blank=True, related_name="changes_to")
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=12, default="APPLIED", choices=[("PENDING","Pending review"),("APPLIED","Applied"),("APPROVED","Approved"),("REJECTED","Rejected")])
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_enrollment_changes")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class CORVersion(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="cor_versions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    reason = models.CharField(max_length=200, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["enrollment","version"], name="unique_cor_version")]
        ordering = ["-version"]

class AssessmentVersion(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="assessment_versions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["enrollment","version"], name="unique_assessment_version")]
        ordering = ["-version"]


class AcademicRecord(models.Model):
    RECORD_TYPES = [("ADMISSION", "Admission"), ("ENROLLMENT", "Enrollment"), ("YEAR_LEVEL", "Year-level update"), ("STANDING", "Academic standing"), ("GRADUATION", "Graduation"), ("TRANSFER", "Transfer / credit evaluation")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="academic_records")
    term = models.ForeignKey(SchoolTerm, on_delete=models.PROTECT, null=True, blank=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT, null=True, blank=True)
    year_level = models.PositiveSmallIntegerField(null=True, blank=True)
    record_type = models.CharField(max_length=16, choices=RECORD_TYPES)
    status = models.CharField(max_length=30, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-effective_date", "-created_at", "-id"]
    def __str__(self):
        return f"{self.student.student_id} · {self.get_record_type_display()} · {self.status}"


class FinancialAdjustment(models.Model):
    KINDS = [("SCHOLARSHIP", "Scholarship"), ("WAIVER", "Fee waiver"), ("CHARGE", "Additional charge"), ("REFUND", "Refund")]
    STATUSES = [("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="financial_adjustments")
    kind = models.CharField(max_length=12, choices=KINDS)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="PENDING")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_financial_adjustments")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_financial_adjustments")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]
    def __str__(self):
        return f"{self.get_kind_display()} · ₱{self.amount} · {self.enrollment}"


class AdmissionApplication(models.Model):
    STATUSES = [("PENDING", "Pending review"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")]
    first_name = models.CharField(max_length=80)
    middle_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80)
    birth_date = models.DateField(null=True, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    term = models.ForeignKey(SchoolTerm, on_delete=models.PROTECT)
    admission_category = models.CharField(max_length=20, choices=[("FRESHMAN", "Freshman"), ("TRANSFEREE", "Transferee"), ("RETURNING", "Returning"), ("SHIFTY", "Shifty")], default="FRESHMAN")
    status = models.CharField(max_length=10, choices=STATUSES, default="PENDING")
    notes = models.TextField(blank=True)
    created_student = models.OneToOneField(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="admission_application")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
    def __str__(self):
        return f"{self.last_name}, {self.first_name} · {self.get_status_display()}"
