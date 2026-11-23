# Normalized ERD — Crow's Foot Relationship Specification

`||` = exactly one, `o|` = zero or one, `|{` = one or many, `o{` = zero or many.

```text
DEPARTMENT ||——o{ PROGRAM
PROGRAM ||——o{ STUDENT
PROGRAM ||——o{ CURRICULUM_SUBJECT
SUBJECT ||——o{ CURRICULUM_SUBJECT
CURRICULUM_SUBJECT }o——o{ SUBJECT : prerequisites
SCHOOL_TERM ||——o{ SECTION
PROGRAM ||——o{ SECTION
SECTION ||——o{ SUBJECT_OFFERING
CURRICULUM_SUBJECT ||——o{ SUBJECT_OFFERING
INSTRUCTOR ||——o{ SUBJECT_OFFERING
SUBJECT_OFFERING ||——o{ CLASS_SCHEDULE
ROOM ||——o{ CLASS_SCHEDULE
STUDENT ||——o{ ENROLLMENT
SCHOOL_TERM ||——o{ ENROLLMENT
ENROLLMENT ||——o{ ENROLLMENT_SUBJECT
SUBJECT_OFFERING ||——o{ ENROLLMENT_SUBJECT
ENROLLMENT ||——o{ ENROLLMENT_CHANGE
ENROLLMENT ||——o{ ASSESSMENT_ITEM
ENROLLMENT ||——o{ ASSESSMENT_VERSION
FEE ||——o{ ASSESSMENT_ITEM
ENROLLMENT ||——o{ PAYMENT
ENROLLMENT ||——o{ COR_VERSION
ENROLLMENT_SUBJECT ||——o| GRADE
STUDENT ||——o{ STUDENT_DOCUMENT
SCHOOL_TERM o|——o{ STUDENT_DOCUMENT
USER ||——o| STUDENT
USER ||——o| INSTRUCTOR
USER ||——o{ PAYMENT : recorded_by
USER ||——o{ AUDIT_LOG
USER ||——o{ COR_VERSION : issued_by
USER ||——o{ ENROLLMENT_CHANGE : changed_by
```

## Key attributes

- **Student**: unique `student_id`, name, program FK, year level, admission category, enrollment standing, account status and first-login password-change flag.
- **SchoolTerm**: semester, academic year, dates, enrollment/add/drop windows, open flag, passing-grade threshold and min/max units.
- **CurriculumSubject**: program, subject, year level, semester and many-to-many prerequisite subjects.
- **SubjectOffering**: curriculum subject, section, instructor and capacity.
- **EnrollmentChange**: change type, affected subject, from/to offering, reason, status, actor and timestamp.
- **AssessmentVersion**: numbered JSON snapshot of assessment items and total.
- **Payment**: amount, method, reference, verification status, recorder and verifier.
- **CORVersion**: numbered JSON snapshot, reason, issuer and timestamp.
- **StudentDocument**: student/term, document type, private file path, status, reviewer and timestamp.

AssessmentVersion and CORVersion intentionally preserve historical snapshots. Payment remains a separate ledger; only verified payments reduce the displayed balance. Student documents are downloaded through an authenticated ownership-checked view.
