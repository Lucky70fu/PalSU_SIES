# Generated for expanded student, finance, and payment workflows.
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import core.validators


def populate_existing_verified_receipts(apps, schema_editor):
    Payment = apps.get_model("core", "Payment")
    for payment in Payment.objects.filter(verification_status="VERIFIED", receipt_number__isnull=True).iterator():
        paid_at = payment.paid_at
        date_part = paid_at.strftime("%Y%m") if paid_at else "LEGACY"
        payment.receipt_number = f"OR-{date_part}-{payment.pk:06d}"
        payment.save(update_fields=["receipt_number"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_expand_student_select_choices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="fee", name="category",
            field=models.CharField(choices=[("TUITION", "Tuition"), ("MISC", "Miscellaneous"), ("LAB", "Laboratory"), ("LIBRARY", "Library"), ("OTHER", "Other")], default="OTHER", max_length=12),
        ),
        migrations.AddField(
            model_name="fee", name="program",
            field=models.ForeignKey(blank=True, help_text="Leave blank to apply to all programs.", null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.program"),
        ),
        migrations.AddField(
            model_name="fee", name="term",
            field=models.ForeignKey(blank=True, help_text="Leave blank to apply to all terms.", null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.schoolterm"),
        ),
        migrations.AddField(
            model_name="fee", name="year_level",
            field=models.PositiveSmallIntegerField(blank=True, help_text="Leave blank to apply to all year levels.", null=True),
        ),
        migrations.AddField(
            model_name="payment", name="proof_file",
            field=models.FileField(blank=True, null=True, upload_to="payment_proofs/%Y/%m/", validators=[core.validators.validate_document_upload]),
        ),
        migrations.AddField(
            model_name="payment", name="receipt_number",
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="payment", name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(populate_existing_verified_receipts, noop_reverse),
        migrations.AddField(
            model_name="enrollmentchange", name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_enrollment_changes", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="enrollmentchange", name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="studentdocument", name="file",
            field=models.FileField(blank=True, null=True, upload_to="student_documents/%Y/%m/", validators=[core.validators.validate_document_upload]),
        ),
        migrations.AlterField(
            model_name="enrollmentchange", name="status",
            field=models.CharField(choices=[("PENDING", "Pending review"), ("APPLIED", "Applied"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="APPLIED", max_length=12),
        ),
        migrations.CreateModel(
            name="AcademicRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year_level", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("record_type", models.CharField(choices=[("ADMISSION", "Admission"), ("ENROLLMENT", "Enrollment"), ("YEAR_LEVEL", "Year-level update"), ("STANDING", "Academic standing"), ("GRADUATION", "Graduation"), ("TRANSFER", "Transfer / credit evaluation")], max_length=16)),
                ("status", models.CharField(blank=True, max_length=30)),
                ("effective_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("program", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="core.program")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="academic_records", to="core.student")),
                ("term", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="core.schoolterm")),
            ],
            options={"ordering": ["-effective_date", "-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="AdmissionApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=80)),
                ("middle_name", models.CharField(blank=True, max_length=80)),
                ("last_name", models.CharField(max_length=80)),
                ("birth_date", models.DateField(blank=True, null=True)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("address", models.TextField(blank=True)),
                ("admission_category", models.CharField(choices=[("FRESHMAN", "Freshman"), ("TRANSFEREE", "Transferee"), ("RETURNING", "Returning"), ("SHIFTY", "Shifty")], default="FRESHMAN", max_length=20)),
                ("status", models.CharField(choices=[("PENDING", "Pending review"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="PENDING", max_length=10)),
                ("notes", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("program", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.program")),
                ("term", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.schoolterm")),
                ("created_student", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="admission_application", to="core.student")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="FinancialAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("SCHOLARSHIP", "Scholarship"), ("WAIVER", "Fee waiver"), ("CHARGE", "Additional charge"), ("REFUND", "Refund")], max_length=12)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("reference", models.CharField(blank=True, max_length=100)),
                ("notes", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")], default="PENDING", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_financial_adjustments", to=settings.AUTH_USER_MODEL)),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="financial_adjustments", to="core.enrollment")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_financial_adjustments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
