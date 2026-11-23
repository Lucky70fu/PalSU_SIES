from decimal import Decimal
from django import forms
from django.db.models import Sum
from .models import Student, Enrollment, EnrollmentSubject, Payment, StudentDocument, Grade, SubjectOffering, FinancialAdjustment, AdmissionApplication
from .validators import validate_document_upload

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["first_name","middle_name","last_name","birth_date","gender","email","phone","address","program","year_level","admission_category","enrollment_standing"]
        widgets = {"birth_date": forms.DateInput(attrs={"type":"date"})}

class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["student","term","enrollment_type"]

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["enrollment","amount","method","reference_no"]
        help_texts = {
            "amount": "Partial installments are accepted. Multiple payments may be recorded, up to the assessed balance.",
        }

    def clean(self):
        cleaned = super().clean()
        enrollment = cleaned.get("enrollment")
        amount = cleaned.get("amount")
        if not enrollment or amount is None:
            return cleaned

        from .services import financial_totals
        assessed = financial_totals(enrollment)["assessment"]
        already_committed = enrollment.payments.filter(
            verification_status__in=["PENDING", "VERIFIED"]
        ).exclude(pk=self.instance.pk).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        refunds = financial_totals(enrollment)["refunds"]
        remaining = assessed - max(already_committed - refunds, Decimal("0.00"))
        if assessed <= 0:
            self.add_error("enrollment", "Generate the enrollment assessment before recording a payment.")
        elif amount > remaining:
            self.add_error("amount", f"The amount exceeds the remaining payable balance of ₱{max(remaining, Decimal('0.00')):,.2f}. You may record a smaller partial payment.")
        return cleaned


class StudentDocumentUploadForm(forms.ModelForm):
    DOCUMENTS = [(x, x) for x in ["Grade Card", "Pre-Enrollment Form", "Clearance", "Medical Certificate", "Good Moral Certificate", "PSA/Birth Certificate", "SF9/Form 138", "ID Picture", "Notice of Admission", "Shifting Form", "Previous Clearance", "Transcript of Records", "Admission Form", "Certificate of Transfer", "Readmission Form", "Guidance Office document", "Subject Accreditation document"]]
    document_type = forms.ChoiceField(choices=DOCUMENTS)
    class Meta:
        model = StudentDocument
        fields = ["term", "document_type", "file", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["term"].required = True
        self.fields["file"].required = True
    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        return validate_document_upload(uploaded)


class StudentPaymentSubmissionForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["enrollment", "amount", "method", "reference_no", "proof_file"]
        help_texts = {"proof_file": "Upload a clear PDF, PNG, or JPEG receipt/screenshot (maximum 5 MB)."}
        widgets = {"proof_file": forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg"})}

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        self.fields["method"].choices = [(x, label) for x, label in Payment.METHOD if x in ("GCASH", "MAYA", "BANK")]
        self.fields["enrollment"].queryset = Enrollment.objects.filter(student=student, status__in=["APPROVED", "ENROLLED"]) if student else Enrollment.objects.none()
        self.fields["proof_file"].required = True
        self.fields["reference_no"].required = True

    def clean_proof_file(self):
        return validate_document_upload(self.cleaned_data.get("proof_file"))

    def clean(self):
        cleaned = super().clean()
        enrollment, amount = cleaned.get("enrollment"), cleaned.get("amount")
        if enrollment and amount is not None:
            from .services import financial_totals
            assessed = financial_totals(enrollment)["assessment"]
            committed = enrollment.payments.filter(verification_status__in=["PENDING", "VERIFIED"]).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
            refunds = financial_totals(enrollment)["refunds"]
            committed = max(committed - refunds, Decimal("0.00"))
            if assessed <= 0:
                self.add_error("enrollment", "The Registrar/Cashier must generate the assessment first.")
            elif amount > max(assessed - committed, Decimal("0.00")):
                self.add_error("amount", f"Amount exceeds the remaining payable balance of ₱{max(assessed - committed, Decimal('0.00')):,.2f}.")
        return cleaned


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ["prelim", "midterm", "final", "remarks"]
        widgets = {field: forms.NumberInput(attrs={"step": "0.01", "min": "1.00", "max": "5.00"}) for field in ("prelim", "midterm", "final")}

    def clean(self):
        cleaned = super().clean()
        for name in ("prelim", "midterm", "final"):
            value = cleaned.get(name)
            if value is not None and not Decimal("1.00") <= value <= Decimal("5.00"):
                self.add_error(name, "Grade must be between 1.00 and 5.00.")
        return cleaned


class FinancialAdjustmentForm(forms.ModelForm):
    class Meta:
        model = FinancialAdjustment
        fields = ["enrollment", "kind", "amount", "reference", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

class EnrollmentChangeRequestForm(forms.Form):
    change_type = forms.ChoiceField(choices=[("ADD", "Add subject"), ("DROP", "Drop subject")])
    offering = forms.ModelChoiceField(queryset=SubjectOffering.objects.none(), label="Subject / Section")
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=True)


class AdmissionApplicationForm(forms.ModelForm):
    class Meta:
        model = AdmissionApplication
        fields = ["first_name", "middle_name", "last_name", "birth_date", "email", "phone", "address", "program", "term", "admission_category"]
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"}), "address": forms.Textarea(attrs={"rows": 3})}
