# Architecture and Workflow Diagrams

## System architecture

```mermaid
flowchart TB
  Browser[Student / Registrar / Cashier / Instructor / Administrator Browser]
  Templates[HTML Templates + Orange CSS + JavaScript]
  Views[Django Views and Forms]
  Services[Enrollment / Prerequisite / Assessment / COR Services]
  Auth[Django Authentication, Groups and Permissions]
  ORM[Django ORM]
  DB[(SQLite local / MySQL deployment)]
  Files[(Private Student Document Storage)]
  Reports[ReportLab PDF / OpenPyXL Excel / CSV]
  Browser --> Templates --> Views
  Views --> Auth
  Views --> Services
  Views --> ORM --> DB
  Views --> Files
  Views --> Reports
```

## Context diagram

```mermaid
flowchart LR
  Student[Student] -->|Profile, proposed subjects, documents| SIS((Enrollment System))
  SIS -->|Application status, schedule, assessment, COR, grades| Student
  Registrar[Registrar] -->|Student records, curriculum, review decision| SIS
  SIS -->|Enrollment queue, missing documents, reports| Registrar
  Cashier[Cashier] -->|Payment record and verification decision| SIS
  SIS -->|Verified balance and collection reports| Cashier
  Instructor[Instructor] -->|Authorized grade data| SIS
  SIS -->|Assigned schedule and class data| Instructor
  Admin[Administrator] -->|Users, roles and system configuration| SIS
  SIS -->|Audit and operational reports| Admin
```

## DFD Level 0

```mermaid
flowchart TB
  S[Student] --> P1((1.0 Student Registration and Documents))
  P1 <--> D1[(Student Records)]
  R[Registrar] --> P2((2.0 Academic Setup and Enrollment Review))
  P2 <--> D2[(Programs, Curriculum, Terms, Offerings)]
  P1 --> P3((3.0 Subject Assignment and Enrollment))
  D1 --> P3
  D2 --> P3
  P3 <--> D3[(Enrollment and Enrollment Changes)]
  C[Cashier] --> P4((4.0 Assessment and Payment))
  P3 --> P4
  P4 <--> D4[(Assessment Versions and Payment Ledger)]
  I[Instructor] --> P5((5.0 Grade Management))
  P5 <--> D5[(Grades)]
  P3 --> P6((6.0 COR and Reporting))
  P4 --> P6
  P5 --> P6
  P6 --> D6[(COR Versions and Audit Logs)]
```

## DFD Level 1 — enrollment processing

```mermaid
flowchart TB
  A[Student login] --> B[Find active school term]
  B --> C[Load curriculum and passing grades]
  C --> D[Resolve prerequisites recursively]
  D --> E[Select official available offerings]
  E --> F[Build proposed subject list]
  F --> G[Student adds, drops or changes section in draft]
  G --> H[Revalidate duplicates, prerequisites, schedule, capacity and units]
  H --> I{Valid?}
  I -- No --> G
  I -- Yes --> J[Submit enrollment]
  J --> K[Registrar reviews verified documents]
  K --> L{Approve?}
  L -- No --> M[Reject / return for correction]
  L -- Yes --> N[Mark enrolled, recalculate assessment, issue COR snapshot]
```

## Activity — prerequisite checking and replacement

```mermaid
flowchart TD
  A([Start]) --> B[Read curriculum subject]
  B --> C{Subject already passed?}
  C -- Yes --> Z[Skip subject]
  C -- No --> D[Read all prerequisites]
  D --> E{Prerequisite passed or already proposed?}
  E -- Yes --> F[Continue checking remaining prerequisites]
  E -- No --> G[Search official offering for missing prerequisite]
  G --> H{Offering exists, seat available and schedule valid?}
  H -- Yes --> I[Recursively validate prerequisite chain]
  I --> J[Add earliest eligible prerequisite]
  H -- No --> K[Record Registrar review warning]
  J --> F
  F --> L{All prerequisites satisfied?}
  L -- Yes --> M[Keep dependent subject eligible]
  L -- No --> N[Defer dependent subject and explain replacement]
  M --> Z
  N --> Z
  K --> Z
```

## Activity — payment and assessment

```mermaid
flowchart TD
  A([Start]) --> B[Recalculate fee items using Decimal]
  B --> C[Store assessment version when changed]
  C --> D[Cashier records payment]
  D --> E[Payment status Pending]
  E --> F{Cashier verifies?}
  F -- No --> G[Mark Rejected]
  F -- Yes --> H[Mark Verified and record verifier/time]
  H --> I[Recompute verified payments and balance]
  G --> I
  I --> J[Show updated balance and preserve payment history]
  J --> K([End])
```

## Scope notes

- Public admission intake and Registrar approval, academic-history records, student draft planner, prerequisite recursion, document submission/verification, Registrar approval, assessment snapshots, and versioned COR are implemented.
- Post-approval add/drop requests are submitted by students and applied only after Registrar approval during the configured add/drop period; assessment and COR are revised.
- Instructor rosters and assigned-class grade encoding are implemented with server-side ownership checks.
- ClassSchedule validation is invoked on model save and serializes conflicting room/instructor writes with row locks where supported. Database-specific exclusion constraints remain a recommended production hardening.
- Student payment proof upload, Cashier/Administrator verification and internal acknowledgment receipts are implemented. Live provider checkout and provider-specific signed webhooks require merchant onboarding and credentials.
- The Reports page provides 12 operational/financial report datasets with CSV/Excel/PDF export.


## Password recovery

Students and staff (including instructors, cashiers, registrars, and administrators) can request a password reset from the shared login page using the email address registered to their user account. Django generates a single-use, time-limited token and sends the reset link. Registrar/Administrator users can trigger the same email workflow from a student profile. Staff do not view or choose the student's password. Local development uses the console email backend, which prints messages in the server terminal; actual email delivery requires institution-approved SMTP settings.
