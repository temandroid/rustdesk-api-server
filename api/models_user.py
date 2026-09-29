from django.db import models
from django.contrib.auth.models import (
    BaseUserManager, AbstractBaseUser, PermissionsMixin
)


class MyUserManager(BaseUserManager):
    def create_user(self, username, password=None):
        if not username:
            raise ValueError('Users must have a username')

        user = self.model(username=username,
        )
 
        user.set_password(password)
        user.save(using=self._db)
        return user
 
    def create_superuser(self, username, password):
        user = self.create_user(username,
            password=password,
            
        )
        user.is_admin = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class UserProfile(AbstractBaseUser, PermissionsMixin):
    username = models.CharField('Username', 
                                unique=True,
                                max_length=50)
    
    rid = models.CharField(verbose_name='RustDesk ID', max_length=16)
    uuid = models.CharField(verbose_name='uuid', max_length=60)
    autoLogin = models.BooleanField(verbose_name='Auto Login', default=True)
    rtype = models.CharField(verbose_name='Type', max_length=20)
    deviceInfo = models.TextField(verbose_name='Login Information:', blank=True)
    
    is_active = models.BooleanField(verbose_name='Active', default=True)
    is_admin = models.BooleanField(verbose_name='Admin', default=False)

    objects = MyUserManager()
 
    USERNAME_FIELD = 'username'  # Field used as username
    REQUIRED_FIELDS = []  # Fields prompted by createsuperuser besides username and password
    
    
    def get_full_name(self):
        # The user is identified by their username
        return self.username
 
    def get_short_name(self):
        # The user is identified by their username
        return self.username
 
    def __str__(self):  # __unicode__ on Python 2
        return self.username
 
    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission? Only active admins have any."
        return self.is_active and self.is_admin

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        return self.is_active and self.is_admin
        


    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff 
        return self.is_admin

    class Meta:
    
        verbose_name = "User"
        verbose_name_plural = "User List"
        permissions = (
            ("view_task", "Can see available tasks"),
            ("change_task_status", "Can change the status of tasks"),
            ("close_task", "Can remove a task by setting its status as closed"),
        )
