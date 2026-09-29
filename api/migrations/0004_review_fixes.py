from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_rustdesdevice_ip_rustdeskpeer_ip'),
    ]

    operations = [
        migrations.RenameModel(old_name='RustDesDevice', new_name='RustDeskDevice'),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='cpu',
            field=models.CharField(max_length=255, verbose_name='CPU'),
        ),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='hostname',
            field=models.CharField(max_length=255, verbose_name='Hostname'),
        ),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='memory',
            field=models.CharField(max_length=60, verbose_name='Memory'),
        ),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='os',
            field=models.CharField(max_length=255, verbose_name='Operating System'),
        ),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='username',
            field=models.CharField(blank=True, max_length=100, verbose_name='System Username'),
        ),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='version',
            field=models.CharField(max_length=60, verbose_name='Client Version'),
        ),
        migrations.AlterField(
            model_name='rustdeskdevice',
            name='ip',
            field=models.CharField(default='', max_length=45, verbose_name='IP Address'),
        ),
        migrations.AlterField(
            model_name='rustdeskpeer',
            name='username',
            field=models.CharField(max_length=100, verbose_name='System Username'),
        ),
        migrations.AlterField(
            model_name='rustdeskpeer',
            name='hostname',
            field=models.CharField(max_length=100, verbose_name='Operating System Name'),
        ),
        migrations.AlterField(
            model_name='rustdeskpeer',
            name='alias',
            field=models.CharField(max_length=100, verbose_name='Alias'),
        ),
        migrations.AlterField(
            model_name='rustdeskpeer',
            name='platform',
            field=models.CharField(max_length=60, verbose_name='Platform'),
        ),
        migrations.AlterField(
            model_name='rustdeskpeer',
            name='tags',
            field=models.TextField(blank=True, verbose_name='Tags'),
        ),
        migrations.AlterField(
            model_name='rustdeskpeer',
            name='ip',
            field=models.CharField(blank=True, default='', max_length=45, verbose_name='IP Address'),
        ),
        migrations.AlterField(
            model_name='rustdesktoken',
            name='username',
            field=models.CharField(max_length=50, verbose_name='Username'),
        ),
        migrations.AlterField(
            model_name='sharelink',
            name='peers',
            field=models.TextField(verbose_name='Machine ID List'),
        ),
        migrations.AlterField(
            model_name='connlog',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='connlog',
            name='from_ip',
            field=models.CharField(max_length=45, null=True, verbose_name='From IP'),
        ),
        migrations.AlterField(
            model_name='filelog',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='filelog',
            name='user_ip',
            field=models.CharField(default='0', max_length=45, verbose_name='User IP'),
        ),
    ]
