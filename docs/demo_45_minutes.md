# 45-Minute Demonstration Plan

| Time | Topic | What to show |
|---|---|---|
| 0–4 min | Introduction | Problem, objectives, scope and user roles |
| 4–9 min | Technology and architecture | Django/Python, ORM, SQLite/MySQL configuration, authentication and architecture diagram |
| 9–14 min | Database design | ERD, normalization, prerequisites and DFD |
| 14–19 min | Academic setup | Colleges, programs, subjects, curriculum, terms, instructors, rooms, sections and offerings |
| 19–24 min | Student registration | Generated Student ID, portal account and forced first-login password change |
| 24–31 min | Student enrollment | Auto-proposed subjects, recursive prerequisite chain, draft add/drop/section, capacity checks and validation |
| 31–36 min | Registrar and documents | Document upload/status review, enrollment validation and approval |
| 36–40 min | Finance and COR | Student online proof upload, Cashier verification, internal receipt, scholarship/refund adjustment, balance and COR version |
| 40–43 min | Reports and audit | 12 CSV/Excel/PDF reports, instructor roster/grade encoding and audit events |
| 43–45 min | Limitations and Q&A | Explain that live GCash/Maya checkout/webhooks still require merchant credentials; discuss production security and institutional policy configuration |

## Demo data

Run `python manage.py seed_demo_data`. Demo credentials are listed in the root README. The command is idempotent and creates fictional starter data; it does not create every sample scenario in the master specification.

## Technology references

- Django documentation: https://docs.djangoproject.com/en/5.2/
- Python documentation: https://docs.python.org/3/
- MySQL documentation: https://dev.mysql.com/doc/
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/
