import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def fill_uuids(apps, schema_editor):
    Comment = apps.get_model("problems", "Comment")
    Like = apps.get_model("problems", "Like")
    UpdateProblem = apps.get_model("problems", "UpdateProblem")

    for model in (Comment, UpdateProblem):
        rows = list(model.objects.only("pk"))
        for row in rows:
            row.new_id = uuid.uuid4()
        model.objects.bulk_update(rows, ["new_id"], batch_size=500)

    Like.objects.update(
        new_comment=Subquery(
            Comment.objects.filter(pk=OuterRef("comment_id")).values("new_id")
        )
    )


def drop_integer_ids(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        return

    for name in ("Comment", "UpdateProblem"):
        table = apps.get_model("problems", name)._meta.db_table
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table)} DROP COLUMN id"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("problems", "0009_updateproblem_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="new_id",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="updateproblem",
            name="new_id",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="like",
            name="new_comment",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(fill_uuids),
        migrations.RemoveConstraint(
            model_name="like",
            name="unique_user_comment_like",
        ),
        migrations.RemoveField(
            model_name="like",
            name="comment",
        ),
        migrations.RunPython(drop_integer_ids),
        migrations.AlterField(
            model_name="comment",
            name="new_id",
            field=models.UUIDField(
                default=uuid.uuid4, primary_key=True, serialize=False
            ),
        ),
        migrations.AlterField(
            model_name="updateproblem",
            name="new_id",
            field=models.UUIDField(
                default=uuid.uuid4, primary_key=True, serialize=False
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="comment", name="id"),
                migrations.RemoveField(model_name="updateproblem", name="id"),
            ],
        ),
        migrations.RenameField(
            model_name="comment",
            old_name="new_id",
            new_name="id",
        ),
        migrations.RenameField(
            model_name="updateproblem",
            old_name="new_id",
            new_name="id",
        ),
        migrations.RenameField(
            model_name="like",
            old_name="new_comment",
            new_name="comment",
        ),
        migrations.AlterField(
            model_name="like",
            name="comment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="likes",
                to="problems.comment",
            ),
        ),
        migrations.AddConstraint(
            model_name="like",
            constraint=models.UniqueConstraint(
                fields=("user", "comment"), name="unique_user_comment_like"
            ),
        ),
    ]
