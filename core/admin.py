from django.contrib import admin
from .models import *
admin.site.register([Department, Program, Student, SchoolTerm, Subject, CurriculumSubject, Instructor, Room, Section, SubjectOffering, ClassSchedule, Enrollment, EnrollmentSubject, Fee, AssessmentItem, Payment, Grade, AuditLog, StudentDocument, EnrollmentChange, CORVersion, AssessmentVersion, AcademicRecord, FinancialAdjustment, AdmissionApplication])
