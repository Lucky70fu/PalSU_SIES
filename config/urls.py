from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("admissions/apply/", views.admission_apply, name="admission_apply"),
    path("admissions/", views.admission_applications, name="admission_applications"),
    path("admissions/<int:pk>/review/", views.admission_application_review, name="admission_application_review"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/password/reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.txt",
        subject_template_name="registration/password_reset_subject.txt",
        html_email_template_name="registration/password_reset_email.html",
        success_url=reverse_lazy("password_reset_done")), name="password_reset"),
    path("accounts/password/reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html"), name="password_reset_done"),
    path("accounts/password/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
        success_url=reverse_lazy("password_reset_complete")), name="password_reset_confirm"),
    path("accounts/password/reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html"), name="password_reset_complete"),
    path("students/<int:pk>/send-password-reset/", views.student_send_password_reset,
        name="student_send_password_reset"),
    path("accounts/password/change/", views.StudentPasswordChangeView.as_view(
        template_name="registration/password_change_form.html",
        success_url=reverse_lazy("password_change_done")), name="password_change"),
    path("accounts/password/change/done/", auth_views.PasswordChangeDoneView.as_view(
        template_name="registration/password_change_done.html"), name="password_change_done"),
    path("", views.dashboard, name="dashboard"),
    path("students/", views.student_list, name="student_list"),
    path("students/documents/", views.student_documents, name="student_documents"),
    path("students/documents/<int:pk>/download/", views.student_document_download, name="student_document_download"),
    path("students/new/", views.student_create, name="student_create"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("students/<int:pk>/edit/", views.student_edit, name="student_edit"),
    path("students/<int:pk>/create-account/", views.student_create_portal_account, name="student_create_portal_account"),
    path("students/<int:pk>/delete/", views.student_delete, name="student_delete"),
    path("manage/<slug:slug>/", views.managed_list, name="managed_list"),
    path("manage/<slug:slug>/new/", views.managed_form, name="managed_create"),
    path("manage/<slug:slug>/<int:pk>/edit/", views.managed_form, name="managed_edit"),
    path("manage/<slug:slug>/<int:pk>/delete/", views.managed_delete, name="managed_delete"),
    path("academics/", views.academic_overview, name="academic_overview"),
    path("enrollments/", views.enrollment_list, name="enrollment_list"),
    path("enrollments/new/", views.enrollment_create, name="enrollment_create"),
    path("enrollments/planner/", views.enrollment_planner, name="enrollment_planner"),
    path("my-enrollment/", views.student_enrollment_portal, name="student_enrollment_portal"),
    path("my-enrollment/<int:pk>/form/", views.student_enrollment_form, name="student_enrollment_form"),
    path("enrollments/<int:pk>/review/", views.enrollment_review, name="enrollment_review"),
    path("enrollments/<int:pk>/cor/", views.cor_list, name="cor_list"),
    path("enrollments/<int:pk>/cor/<int:version>/", views.cor_print, name="cor_print"),
    path("billing/payment/<int:pk>/verify/", views.payment_verify, name="payment_verify"),
    path("billing/payment/<int:pk>/proof/", views.payment_proof_download, name="payment_proof_download"),
    path("billing/payment/<int:pk>/receipt/", views.payment_receipt, name="payment_receipt"),
    path("billing/adjustments/new/", views.financial_adjustment_create, name="financial_adjustment_create"),
    path("billing/adjustments/<int:pk>/review/", views.financial_adjustment_review, name="financial_adjustment_review"),
    path("billing/", views.billing_list, name="billing_list"),
    path("billing/payment/", views.record_payment, name="record_payment"),
    path("enrollments/<int:pk>/changes/request/", views.enrollment_change_request, name="enrollment_change_request"),
    path("enrollments/changes/", views.enrollment_changes, name="enrollment_changes"),
    path("enrollments/changes/<int:pk>/review/", views.enrollment_change_review, name="enrollment_change_review"),
    path("grades/<int:pk>/edit/", views.grade_edit, name="grade_edit"),
    path("schedules/", views.schedule_list, name="schedule_list"),
    path("grades/", views.grade_list, name="grade_list"),
    path("reports/", views.reports, name="reports"),
]
