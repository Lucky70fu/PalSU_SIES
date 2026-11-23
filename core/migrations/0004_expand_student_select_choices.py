from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_payment_verification_status_payment_verified_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="admission_category",
            field=models.CharField(
                choices=[
                    ("FRESHMAN", "Freshman"),
                    ("TRANSFEREE", "Transferee"),
                    ("RETURNING", "Returning"),
                    ("SHIFTY", "Shifty"),
                    ("REGULAR", "Continuing Student"),
                ],
                default="REGULAR",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="student",
            name="account_status",
            field=models.CharField(
                choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive"), ("GRADUATED", "Graduated")],
                default="ACTIVE",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="student",
            name="enrollment_standing",
            field=models.CharField(
                choices=[("REGULAR", "Regular"), ("IRREGULAR", "Irregular"), ("PROBATIONARY", "Probationary")],
                default="REGULAR",
                max_length=20,
            ),
        ),
    ]
