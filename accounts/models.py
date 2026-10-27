from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    full_name = models.CharField(max_length=150, blank=True, null=True)
    role = models.CharField(max_length=10, choices=[('teacher','Ustoz'),('student','Oquvchi')], default='student')
    subject = models.CharField(max_length=100, blank=True, null=True)
    grade = models.CharField(max_length=10, default='barcha')
    letter = models.CharField(max_length=10, default='barchasi')
    monthly_champion_count = models.PositiveIntegerField(default=0)

    # Ustozlar uchun Google Auth va Shaxsiy Google Cloud ma'lumotlari
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    google_email = models.EmailField(blank=True, null=True)
    google_access_token = models.TextField(blank=True, null=True)
    google_refresh_token = models.TextField(blank=True, null=True)
    google_cloud_folder_id = models.CharField(max_length=255, blank=True, null=True)
    google_cloud_bucket = models.CharField(max_length=255, blank=True, null=True)

    def is_teacher(self): return self.role == 'teacher'
    def get_display_name(self):
        name = self.full_name if self.full_name else self.username
        if self.role == 'student' and self.monthly_champion_count > 0:
            if self.monthly_champion_count == 1:
                return f"{name} 👑 (Chempion)"
            else:
                return f"{name} 👑 ({self.monthly_champion_count}xChempion)"
        return name

class Test(models.Model):
    TEST_TYPES = [
        ('exam', 'Nazorat ishi'),
        ('practice', 'Mashg`ulot (qayta-qayta urinish)'),
        ('survey', 'So`rovnoma'),
        ('anonymous', 'Anonim so`rovnoma')
    ]
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=100)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tests')
    status = models.CharField(max_length=12, choices=[('draft','Qoralama'),('published','Faol'),('closed','Yakunlangan')], default='draft')
    test_type = models.CharField(max_length=15, choices=TEST_TYPES, default='exam')
    duration_minutes = models.PositiveIntegerField(default=45)
    start_time = models.DateTimeField(default=timezone.now)
    deadline = models.DateTimeField(null=True, blank=True)
    target_grade = models.CharField(max_length=10, default='barcha')
    target_letter = models.CharField(max_length=10, default='barchasi')
    allow_teachers = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # O'qituvchining shaxsiy Google Cloud (Drive / GCS) integratsiyasi
    teacher_cloud_file_id = models.CharField(max_length=255, blank=True, null=True)
    teacher_cloud_url = models.URLField(max_length=500, blank=True, null=True)
    teacher_cloud_provider = models.CharField(max_length=50, default='teacher_google_cloud')
    cloud_synced_at = models.DateTimeField(null=True, blank=True)

    def is_owner(self, user): return user.is_authenticated and self.creator_id == user.id

class Question(models.Model):
    Q_TYPES = [
        ('single', 'Yagona tanlov'),
        ('multiple', 'Bir nechta tanlov'),
        ('open', 'Ochiq savol (qisqa yozma javob)')
    ]
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    question_type = models.CharField(max_length=10, choices=Q_TYPES, default='single')
    points = models.FloatField(default=1.0)
    order = models.PositiveIntegerField(default=1)
    correct_text_answers = models.TextField(blank=True, null=True)
    class Meta: ordering = ['order', 'id']

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

class TestAttempt(models.Model):
    STATUS = [('in_progress','Ishlanmoqda'),('blocked','Bloklangan'),('completed','Yakunlangan'),('disqualified','Chetlatilgan')]
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attempts', null=True, blank=True)
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='in_progress')
    score = models.FloatField(default=0.0)
    correct_count = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    violation_count = models.PositiveIntegerField(default=0)
    excuse_message = models.TextField(blank=True, null=True)
    attempt_number = models.PositiveIntegerField(default=1)
    def remaining_seconds(self):
        return max(0, int(self.test.duration_minutes * 60 - (timezone.now() - self.started_at).total_seconds()))

class StudentAnswer(models.Model):
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True)
    selected_options = models.ManyToManyField(Option, related_name='multi_selected_answers', blank=True)
    text_answer = models.TextField(blank=True, null=True)

class Complaint(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='complaints')
    reason = models.TextField()
    status = models.CharField(max_length=15, default='pending')
    teacher_comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
