# Functional Requirements and Implementation Mapping

| Area | Implemented | Remaining work / limitation |
|---|---|---|
| Student records and admission | Public admission application, Registrar approval, Student ID/account creation, admission category, profile and academic-history records | Institution-specific entrance exam, admission document checklist and transfer-credit equivalency |
| Academic history | Admission, approved enrollment, program changes, year-level and standing changes; visible on student profile/portal | Full transcript evaluation, graduation clearance and academic honors rules |
| Role access | Server-side role checks; student ownership restrictions; instructor roster ownership | Full external security audit and policy review |
| Academic setup | Colleges, programs, subjects, curriculum, prerequisites, terms, instructors, rooms, sections, offerings and schedules | Curriculum versioning and institutional rule configuration |
| Enrollment | Curriculum proposal, prerequisite validation, schedule checks, unit limits, capacity reservations | Concurrency testing on production database; SQLite does not enforce row locks; pending requests are rechecked before approval |
| Add/Drop | Post-approval student requests; Registrar approval; validation; assessment recalculation; revised COR | Institution-specific appeal/exception workflow |
| Instructor module | Instructor-only class rosters and grade encoding for assigned offerings; student-owned grade display | Grade approval, bulk grade upload, attendance and LMS integration |
| Documents | Authenticated uploads, 5 MB limit, file signature checks, protected download, status review; optional ClamAV hook | Configure and enforce ClamAV in production; private object storage, retention and document versioning |
| Assessment | Fixed/per-unit assessment, approved scholarship/waiver discounts, additional charges, refund ledger, snapshots | More institution-specific fee categories and scholarship eligibility rules |
| Payments | Student proof upload for GCash/Maya/bank transfer, pending/verified/rejected states, Cashier/Admin verification, internal receipt number and printable acknowledgment | Live GCash/Maya checkout, provider-specific webhook and bank reconciliation require merchant credentials and provider testing |
| COR | Initial COR, version history, financial snapshot, revised COR after payment and approved add/drop | Institution-approved document format and digital signature if required |
| Reports | 12 report types with CSV/Excel/PDF export, including balances and reconciliation | Institutional sign-off on definitions and accounting chart-of-accounts integration |
| Audit | Admission, student, enrollment, payment, adjustment, grade and change decisions logged | Change-diff logging, retention policy and tamper-evident external audit storage |


## Test status

The delivered test run reports 8 tests passing and 1 PDF-runtime test skipped in the Linux validation environment. The skip is due to a Windows-specific Pillow binary in the supplied project environment. Install declared requirements on the target machine and rerun `python manage.py test`.

This mapping is deliberately honest: it does not claim every item in the master specification is complete.


## Account recovery

- Student/staff self-service password recovery is available from the login page using the registered email address.
- Students and staff can independently request a one-time password reset email from the shared login page. The registered email must be present on the account.
- Registrar/Administrator can trigger a one-time password reset email from a student profile. The staff member does not see or choose the new password.
- Reset links expire after one hour. Local development prints reset messages in the server terminal; real email requires SMTP configuration.
