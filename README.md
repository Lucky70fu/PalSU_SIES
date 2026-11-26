# PalSU-Inspired Student Information and Online Enrollment System

An existing Django project updated in place for a student information and enrollment academic project. The orange interface and database schema are retained; your local SQLite database is kept separate from the source-only delivery archive. This is a university-inspired academic system, not an official Palawan State University service.

## What is included

- Public prospective-student admission applications, Registrar approval, generated Student IDs, student profiles, portal accounts and academic-history records.
- Five Django Group roles: Administrator, Registrar, Cashier, Instructor and Student.
- Forced password change for newly created student portal accounts; self-service password reset by registered email and Registrar/Administrator-triggered reset links.
- Academic master data: colleges, programs, subjects, curriculum, prerequisites, school terms, instructors, rooms, sections, offerings and schedules.
- Student document and payment-proof upload with PDF/PNG/JPEG signature validation, 5 MB limit, protected download and review status; optional ClamAV integration.
- Student pre-enrollment planner with automatically proposed curriculum subjects, recursive prerequisite checking/replacement, add/drop/section changes in the draft, schedule and capacity checks, unit limits and estimated assessment.
- Student-facing **My Enrolled Subjects & Forms** page with all-term subject lists, enrollment status, saved pre-enrollment form views and direct COR links.
- Read-only student pre-enrollment form / subject-list view for both pending and approved enrollments, including section, instructor and timetable details.
- Registrar approve/reject actions with server-side validation and required verified documents. Approval automatically changes the enrollment to Enrolled, recalculates assessment and issues a versioned COR snapshot.
- Program/term/year-specific fixed or per-unit fee rules, assessment snapshots, approved scholarships/waivers/charges/refunds and verified-payment balance calculations.
- Student dashboard and billing page show verified payments, total assessment, pending payment count and remaining balance.
- Cashier payment verification automatically issues a revised COR version for approved/enrolled students when the verified-payment total changes; prior COR versions are retained and repeated verification does not create duplicates.
- Initial Certificate of Registration (COR) snapshots and version history; automatic, duplicate-safe COR backfill for legacy records already marked Approved or Enrolled.
- Twelve selectable CSV, Excel and PDF operational/financial reports.
- Idempotent demo-data command, automated tests, ERD/DFD/workflow documentation and a 23-slide presentation.

See `docs/requirements_mapping.md` for an honest breakdown of what is implemented and what remains incomplete.

## Technology stack

- Python 3.11 or newer
- Django 5.2
- SQLite for local development
- MySQL 8+ compatibility through `mysqlclient`
- Django ORM and Authentication/Groups
- HTML, CSS and JavaScript
- ReportLab for PDF reports
- OpenPyXL for Excel exports
- python-dotenv for environment variables

## Important preservation note

The updated delivery ZIP is source-only: it deliberately excludes `db.sqlite3`, database backups, `.env`, uploaded media and `.venv`. This prevents accidental replacement of your working student accounts, payment proofs, secret keys or database credentials. Keep your current local `db.sqlite3` and `.env` in your existing project folder. Back up the database before applying the new migration. The new migration adds fields/tables and is designed to preserve existing rows.

## Installation on Windows (PowerShell)

1. Extract the updated ZIP.
2. Open the `enrollment_system` folder in VS Code or PowerShell.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

4. Activate it:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use Command Prompt instead:

   ```bat
   .venv\Scripts\activate.bat
   ```

5. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

6. Create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

7. Copy your existing `db.sqlite3` and `.env` from your current project into the extracted project folder. Do not replace them with an older copy. Keep `DB_NAME=` blank for SQLite.
8. Back up your existing database before migration:

   ```powershell
   Copy-Item db.sqlite3 db.sqlite3.backup
   ```

9. Apply migrations:

   ```powershell
   python manage.py migrate
   ```

10. Check the project and run tests:

   ```powershell
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py test
   ```

11. Repair any existing Enrolled records that are missing a COR (safe to rerun; existing CORs are preserved):

   ```powershell
   python manage.py backfill_missing_cors
   ```

12. Start the server:

   ```powershell
   python manage.py runserver
   ```

13. Open `http://127.0.0.1:8000/`.

## MySQL configuration (optional)

Create a database and configure `.env`:

```sql
CREATE DATABASE enrollment_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```dotenv
DB_NAME=enrollment_db
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_HOST=127.0.0.1
DB_PORT=3306
```

Install a compatible MySQL client/build environment, then run `python manage.py migrate`. Do not point the application at a production database until backups and deployment settings are configured.

## Demo accounts and data

To create fictional sample academic records and role accounts, run:

```powershell
python manage.py seed_demo_data
```

The command is transactional and idempotent. It completes the explicitly named `DEMO-*` academic records, fills the demo student/instructor profile fields, configures enrollment and add/drop windows, creates a prior-term passing grade, creates the current draft enrollment with prerequisite-safe initial subjects, calculates assessment items, adds a pending sample payment, creates the required document checklist, and writes an audit entry. It does not delete existing records or modify non-demo users. Rerunning it resets the five role accounts and two supporting instructor accounts (`demo_instructor_2` and `demo_instructor_3`) to the documented demo password; do not use those accounts for real data.

| Role | Username | Initial password |
|---|---|---|
| Administrator | `demo_administrator` | `DemoPass!2026` |
| Registrar | `demo_registrar` | `DemoPass!2026` |
| Cashier | `demo_cashier` | `DemoPass!2026` |
| Instructor | `demo_instructor` | `DemoPass!2026` |
| Student | `demo_student` | `DemoPass!2026` |
| Supporting instructor | `demo_instructor_2` | `DemoPass!2026` |
| Supporting instructor | `demo_instructor_3` | `DemoPass!2026` |

These credentials are for local classroom demonstration only. The demo student is required to change the initial password on first login. Change or remove demo accounts before deployment.

For existing student records, Registrar/Administrator can use **Create Student Login Account** from the student profile. That legacy account flow uses the student's last name as a temporary password and forces a password change at first login. Do not distribute credentials publicly.

## Password reset workflow

- Students and staff can use **Forgot your password?** on the login page. The system sends a single-use, time-limited Django password-reset link to the account's registered email address.
- Registrar/Administrator users can open a student profile and choose **Send Password Reset Link**. This sends a reset link to the student's registered email; staff never see or set the student's existing password. The student record email is synchronized to the linked portal account before sending when it is populated.
- For local development, the default console email backend prints the reset email and link in the Django terminal. This is for testing only; it does not send real email. For real delivery, configure `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL` in `.env` using the institution's approved SMTP service. Use HTTPS and a production secret key when deployed.
- If a student has no registered email, staff must update the student email first. Password reset does not reveal whether an arbitrary email belongs to an account.

## Main routes

- `/` — role-aware dashboard
- `/students/` — student records
- `/students/documents/` — student document submission/status
- `/academics/` — academic setup
- `/enrollments/` — enrollment applications and Registrar decisions
- `/enrollments/planner/` — student subject planner and editable pre-enrollment form during an open period
- `/my-enrollment/` — student enrollment overview, selected/enrolled subjects and form/COR links
- `/my-enrollment/<id>/form/` — student's read-only pre-enrollment form and subject details
- `/billing/` — assessment and verified-payment balances
- `/schedules/` — schedules
- `/grades/` — grades
- `/reports/` — filtered CSV, Excel and PDF exports
- `/admin/` — Django Admin for advanced configuration

## Typical demonstration workflow

1. Run `seed_demo_data`.
2. Sign in as `demo_administrator` or `demo_registrar` and inspect academic setup.
3. Sign in as `demo_student` and change the initial password.
4. Open Subject Planner. The system proposes eligible prerequisite subjects first where required.
5. Add/drop/change a draft offering and submit the Pre-Enrollment Form.
6. Submit the required documents and have the Registrar mark them Verified in Academic Setup → Student Documents.
7. Registrar approves the enrollment; an initial COR version is generated.
8. Student submits an online payment proof and reference; Cashier/Administrator verifies it. The system issues an internal acknowledgment receipt after verification; only verified payments reduce the balance.
9. For an already approved/enrolled student, payment verification automatically issues a new COR version with the updated verified-payment total and balance. Earlier COR versions remain available in the version history.
10. Student checks the dashboard or Billing & Assessment page for the updated payment total and balance, then opens the latest COR.
11. Export the enrollment report as CSV, Excel or PDF.

## Tests and verification

Validation on the updated source completed successfully: `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and all 28 Django tests passed. Run these commands again on your Windows environment after applying the migration, because your installed Python/Django/database versions may differ.

## Known limitations — read before presenting as complete

- This is an expanded academic project, not a production-certified SIS.
- Public admission application intake and Registrar approval are implemented. Approval creates the Student record, an admission-history entry, and a portal account that requires a password change on first login. Institutional admission documents, entrance-exam scoring and email invitations remain institution-specific extensions.
- Student academic history records admission, approved enrollment, program changes, year-level changes and academic-standing changes. Transcript evaluation, transfer-credit equivalency and graduation clearance still need institution-specific policy rules.
- Post-approval add/drop requests are submitted by the student and applied only after Registrar approval during the configured add/drop period. The system validates units, prerequisites, capacity and schedule conflicts and issues a revised COR.
- Instructor users see rosters for their assigned offerings and can encode prelim/midterm/final grades only for those classes. Administrators retain grade-management access.
- The Reports page provides 12 selectable CSV/Excel/PDF reports: enrollment summary, student masterlist, admission/standing, enrollment status, class rosters, offering capacity, grade distribution, academic performance, assessment ledger, payment collections, outstanding balances and financial reconciliation.
- Students may submit GCash/Maya/bank-transfer reference details and upload a PDF/PNG/JPEG proof. Cashier/Administrator verification is required before the payment counts. The system issues an internal acknowledgment receipt after verification. This is not a live GCash/Maya checkout integration or provider-issued receipt.
- Live GCash/Maya API checkout and provider-specific signed webhooks are not enabled. They require approved merchant accounts, sandbox/production credentials, callback URLs and provider-specific integration testing. Do not put merchant secrets in source control.
- Approved scholarship and fee-waiver adjustments reduce assessed charges; approved additional charges increase the assessment; approved refunds reduce net paid amounts. All adjustments require Cashier/Administrator approval and appear in financial reports.
- Enrollment approval and approved add/drop operations lock offering rows and revalidate seat counts on databases that support row-level locking (such as MySQL). Pending requests may wait in the Registrar queue and are rechecked before approval. SQLite's `select_for_update()` does not provide the same concurrent-write guarantee; use MySQL/PostgreSQL and run concurrency tests before production.
- Schedule validation now checks room and instructor overlaps within the same term and is invoked on model save. A relational database exclusion constraint for time ranges is still recommended for a high-concurrency production deployment.
- PDF/PNG/JPEG uploads are limited to 5 MB and checked against file signatures. Optional ClamAV scanning can be enabled by installing `python-clamd` and setting `CLAMAV_HOST`, `CLAMAV_PORT`, and `CLAMAV_REQUIRED=True`; without a configured scanner, uploads receive type/size validation but are not malware-scanned. Use private storage, HTTPS, retention rules and backups in production.
- Configure HTTPS, `DEBUG=False`, a strong secret, allowed hosts, rate limiting, email verification, least-privilege database accounts and privacy notices before deployment.

## Project structure

- `config/` — settings, middleware and URL routing
- `core/` — models, forms, permissions, business services, views, tests and management commands
- `templates/` — reusable HTML templates and role workflow pages
- `static/css/` — orange theme and responsive styles
- `docs/` — diagrams, requirements mapping, demo script and presentation
- Your existing `db.sqlite3` — keep this local file; it is intentionally excluded from the delivery ZIP.

## References

- Django 5.2: https://docs.djangoproject.com/en/5.2/
- Django authentication and permissions: https://docs.djangoproject.com/en/5.2/topics/auth/
- Django file uploads: https://docs.djangoproject.com/en/5.2/topics/http/file-uploads/
- Python: https://docs.python.org/3/
- MySQL: https://dev.mysql.com/doc/
- OpenPyXL: https://openpyxl.readthedocs.io/
- ReportLab: https://docs.reportlab.com/
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/

- The demo seed creates at least three usable records for relational dropdowns and at least three options for each choice field. It also creates three section choices per demo subject for the student planner. Two supporting instructor accounts (`demo_instructor_2` and `demo_instructor_3`) use the same initial demo password as the documented demo accounts.


### Partial payments and COR access

- Cashiers/Administrators may record multiple installment payments against an enrollment assessment. Each payment may be less than the full balance.
- Pending and verified installments are counted when checking the amount still available to record, preventing duplicate/overpayment entries while a payment is awaiting verification. Rejected payments no longer reserve part of the balance.
- After Registrar approval, students may view and print their COR regardless of whether the assessment is unpaid, partially paid, or fully paid. The COR shows verified payments, payment status, and remaining balance.
- When a payment is verified or rejected after a COR has been issued, the system issues a revised COR version when the financial snapshot changes; prior versions are retained.


### Expanded SIS workflows (2026-11 update)

- **Admission:** `/admissions/apply/` accepts prospective-student applications. Registrar/Administrator reviews them at `/admissions/`; approval creates a student profile and portal login.
- **Academic history:** student profiles and the student portal show admission, enrollment, program, year-level and standing history. Staff can maintain academic-history records from Academic Setup → Academic History Records.
- **Online payment proof:** students use Billing → Submit Online Payment Proof. Only GCash, Maya and bank transfer are available in this student submission form, and a proof file/reference is required. Cashier/Administrator reviews each pending item in Billing.
- **Receipts:** a verified payment receives an internal receipt number and printable acknowledgment at the payment receipt link. It is not an official provider-issued GCash/Maya receipt or a tax-compliant official receipt.
- **Add/drop after approval:** student requests are available from My Enrollment → Request Add/Drop. Registrar/Administrator reviews `/enrollments/changes/`. Approval changes the actual enrollment and issues a new COR version.
- **Instructor gradebook:** Instructor accounts see only their assigned offerings in Grades / My Classes and can encode grades for their own roster.
- **Financial adjustments:** Cashier/Administrator can create scholarships, waivers, additional charges and refunds from Billing. Adjustments affect the account only after approval.
- **Reports:** `/reports/` contains the 12 report types listed in the requirements mapping and supports CSV, Excel and PDF exports.

### Important integration boundary

The payment-proof upload is a manual verification workflow. A live GCash/Maya payment integration is not included because it requires the institution's merchant onboarding, API credentials, sandbox account, provider-specific checkout flow and webhook signing configuration. A manual screenshot/reference must never be described as an automatically authenticated payment.

### Authors
- **Russel Aaron Sarastal (tinapay-aa)**
- **Christian Dave Denzon (Ch8967)**
- **Mark Kevin Sanchez (vioxvanitas)**
- **Ralph Jeffrey Cerdeña (Lucky70fu)**
