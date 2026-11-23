# Database Data Dictionary (Core Entities)

| Entity | Purpose | Important fields / relationships |
|---|---|---|
| Department | College reference | `code` unique, `name` |
| Program | Academic program | `code` unique, `department_id`, `years_to_complete` |
| AdmissionApplication | Prospective student intake | applicant identity/contact, intended program/term, admission category, review status, reviewer, created Student link |
| Student | Student identity/profile | `student_id` unique, user link, names, `program_id`, `year_level`, admission category, enrollment standing, account status |
| AcademicRecord | Admission and academic-history event | student, term/program/year, record type, status, effective date, notes, actor |
| SchoolTerm | Semester configuration | name, school year, start/end dates, enrollment/add-drop windows, passing-grade threshold, min/max units, `is_open` |
| Subject | Subject catalog | `code` unique, title, Decimal units, description |
| CurriculumSubject | Program curriculum placement | program, subject, year level, semester, many-to-many prerequisite subjects |
| Instructor | Instructor profile | user, employee number, department |
| Room | Teaching room | unique room code, capacity |
| Section | Program/term section | code, term, program, year level |
| SubjectOffering | Official subject offering | curriculum subject, section, instructor, capacity |
| ClassSchedule | Meeting slot | offering, day, start/end time, room |
| Enrollment | Student term application | student, term, enrollment type, status, submit time, approver |
| EnrollmentSubject | Selected offering | enrollment, official subject offering |
| EnrollmentChange | Draft and post-approval add/drop history | enrollment, type, subject code, old/new offering, reason, requester, reviewer, status and timestamps |
| Fee | Fee configuration | name/category, Decimal amount, per-unit flag, optional program/term/year-level scope, active flag |
| AssessmentItem | Current assessment line item | enrollment, fee, description, Decimal amount |
| AssessmentVersion | Assessment history | enrollment, version, JSON line-item snapshot, total, timestamp |
| Payment | Financial transaction | enrollment, Decimal amount, method, reference, private proof file, verification status, internal receipt number, rejection reason, recorder, verifier and timestamps |
| FinancialAdjustment | Scholarship/waiver/charge/refund ledger | enrollment, kind, amount, pending/approved/rejected status, creator and reviewer |
| Grade | Official grade record | one-to-one enrollment subject, prelim/midterm/final, remarks |
| StudentDocument | Student-submitted requirement | student, term, type, private file, status, reviewer and updated timestamp |
| CORVersion | Issued COR history | enrollment, version, immutable JSON snapshot, reason, issuer and issue time |
| AuditLog | Accountability event | user, action, object type/id, timestamp |

Django's built-in `User`, `Group`, `Permission` and session tables support authentication and role access. Foreign-key deletion behavior is defined in `core/models.py`; historical payment, COR and enrollment-change records use protective relationships where appropriate.
