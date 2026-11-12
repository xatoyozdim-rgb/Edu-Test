import json
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.db.models import Avg, Count, Q, Max
from functools import wraps

from .models import (
    User, Test, Question, Option,
    TestAttempt, StudentAnswer, Complaint,
    Subject,
)

# ============================================================
# AUTENTIFIKATSIYA
# ============================================================
def teacher_approved_required(view_func):
    """O'qituvchi tasdiqlangan bo'lishi shart"""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_teacher():
            messages.error(request, "Bu sahifa faqat o'qituvchilar uchun.")
            return redirect('dashboard')
        if not request.user.is_approved:
            messages.error(request, "Hisobingiz hali tasdiqlanmagan. Admin tasdiqlashini kuting.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def signup_view(request):
    google_enabled = bool(settings.GOOGLE_CLIENT_ID)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        username = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')
        role = request.POST.get('role', 'student').lower()

        if not username:
            username = email

        if not all([email, password, first_name, last_name]):
            messages.error(request, "Barcha asosiy maydonlarni to'ldirish shart!")
            return render(request, 'accounts/signup.html', {'google_enabled': google_enabled})

        if User.objects.filter(email=email).exists():
            messages.error(request, "Bu email allaqachon ro'yxatdan o'tgan!")
            return render(request, 'accounts/signup.html', {'google_enabled': google_enabled})

        if User.objects.filter(username=username).exists():
            messages.error(request, "Bu login allaqachon band! Boshqa login tanlang.")
            return render(request, 'accounts/signup.html', {'google_enabled': google_enabled})

        full_name = f"{first_name} {last_name}".strip()

        # ============ O'QITUVCHI ============
        if role == 'teacher':
            if google_enabled:
                # Google OAuth mavjud — Google orqali tasdiqlash
                request.session['pending_teacher_signup'] = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'username': username,
                    'full_name': full_name,
                    'password': password,
                }
                return redirect('google_login')
            else:
                # Google OAuth yo'q — to'g'ridan-to'g'ri parol bilan ro'yxatdan o'tish
                                new_teacher = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    full_name=full_name,
                    role='teacher',
                )
                new_teacher.is_approved = False  # ← Admin tasdiqlashi kerak
                new_teacher.save(update_fields=['is_approved'])
                messages.success(
                    request,
                    "Ro'yxatdan o'tdingiz! Admin tasdiqlashini kuting — tasdiqlangach email orqali xabar beriladi."
                )
                return redirect('login')

        # ============ O'QUVCHI ============
        student_class = request.POST.get('student_class', '').strip()
        class_letter = request.POST.get('class_letter', '').strip()

        if not student_class or not class_letter:
            messages.error(request, "O'quvchilar uchun sinf va harf tanlanishi shart!")
            return render(request, 'accounts/signup.html', {'google_enabled': google_enabled})

        User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            role='student',
            grade=student_class,
            letter=class_letter,
        )
        messages.success(request, "Muvaffaqiyatli ro'yxatdan o'tdingiz! Tizimga kiring.")
        return redirect('login')

    return render(request, 'accounts/signup.html', {'google_enabled': google_enabled})


def login_view(request):
    google_enabled = bool(settings.GOOGLE_CLIENT_ID)

    if request.method == 'POST':
        login_input = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

                user_obj = User.objects.filter(username=login_input).first()
        if not user_obj:
            user_obj = User.objects.filter(email=login_input.lower()).first()

        # Bloklangan / tasdiqlanmagan tekshiruvi
        if user_obj and not user_obj.is_active:
            messages.error(request, "Hisobingiz bloklangan. Administrator bilan bog'laning.")
            return render(request, 'accounts/login.html', {'google_enabled': google_enabled})

        if user_obj and user_obj.is_teacher() and not user_obj.is_approved:
            messages.warning(request, "Hisobingiz hali tasdiqlanmagan. Admin tasdiqlashini kuting.")
            return render(request, 'accounts/login.html', {'google_enabled': google_enabled})

        username = user_obj.username if user_obj else login_input

        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            print("=" * 60)
            print(f"LOGIN DEBUG:")
            print(f"  Kiritilgan login: {login_input}")
            print(f"  Topilgan foydalanuvchi: {user.username}")
            print(f"  Full name: {user.full_name}")
            print(f"  User ID: {user.id}")
            login(request, user)
            print(f"  Login dan keyin request.user: {request.user.username}")
            print(f"  request.user.full_name: {request.user.full_name}")
            print(f"  Session key: {request.session.session_key}")
            print(f"  Session dict: {dict(request.session)}")
            print("=" * 60)
            return redirect('dashboard')

        messages.error(request, "Login yoki parol noto'g'ri!")

    return render(request, 'accounts/login.html', {'google_enabled': google_enabled})
def logout_view(request):
    logout(request)
    
    return redirect('login')


def google_login_start(request):
    if not settings.GOOGLE_CLIENT_ID:
        messages.error(
            request,
            "Google orqali kirish hozircha mavjud emas. Login va parol bilan kiring."
        )
        return redirect('login')

    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={settings.GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=email%20profile"
    )
    return redirect(google_auth_url)


def google_login_callback(request):
    code = request.GET.get('code')
    if not code:
        messages.error(request, "Google orqali autentifikatsiyada xatolik yuz berdi.")
        return redirect('login')

    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': settings.GOOGLE_REDIRECT_URI,
                'grant_type': 'authorization_code',
            },
            timeout=10,
        ).json()
    except Exception:
        messages.error(request, "Google bilan aloqa xatosi.")
        return redirect('login')

    access_token = token_response.get('access_token')
    if not access_token:
        messages.error(request, "Google tokenni olish imkoni bo'lmadi.")
        return redirect('login')

    try:
        user_info = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        ).json()
    except Exception:
        messages.error(request, "Google'dan ma'lumot olib bo'lmadi.")
        return redirect('login')

    email = user_info.get('email')
    first_name = user_info.get('given_name', '')
    last_name = user_info.get('family_name', '')

    if not email:
        messages.error(request, "Google profilingizdan email olib bo'lmadi.")
        return redirect('login')

    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'username': email,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': f"{first_name} {last_name}".strip(),
            'role': 'teacher',
        },
    )

    if created:
        pending = request.session.pop('pending_teacher_signup', None)
        if pending:
            user.first_name = pending.get('first_name', first_name)
            user.last_name = pending.get('last_name', last_name)
            user.full_name = pending.get('full_name') or f"{user.first_name} {user.last_name}".strip()
            pending_username = pending.get('username')
            if pending_username and not User.objects.filter(username=pending_username).exclude(id=user.id).exists():
                user.username = pending_username
            user.role = 'teacher'
        user.set_unusable_password()

    # Google tokenlarini saqlash
    user.google_access_token = access_token
    if 'refresh_token' in token_response:
        user.google_refresh_token = token_response['refresh_token']
    user.google_email = email
    user.save()

    login(request, user)
    messages.success(request, f"Xush kelibsiz, {user.get_display_name()}!")
    return redirect('dashboard')


# ============================================================
# DASHBOARD
# ============================================================

@login_required(login_url='login')
def dashboard_view(request):
    user = request.user

    if user.is_teacher():
        total_tests = Test.objects.filter(creator=user).count()
        recent_tests = Test.objects.filter(creator=user).order_by('-created_at')[:5]
        my_attempts = 0
    else:
        total_tests = Test.objects.filter(status='published').count()
        recent_tests = Test.objects.filter(status='published').order_by('-created_at')[:5]
        my_attempts = TestAttempt.objects.filter(
            student=user, status='completed'
        ).count()

    active_students = User.objects.filter(role='student', is_active=True).count()
    completed_tests = TestAttempt.objects.filter(status='completed').count()
    avg_score = TestAttempt.objects.filter(
    status='completed'
).exclude(
    test__test_type__in=['survey', 'anonymous']
).aggregate(avg=Avg('score'))['avg']

    return render(request, 'accounts/dashboard.html', {
        'user': user,
        'total_tests': total_tests,
        'active_students': active_students,
        'completed_tests': completed_tests,
        'average_score': round(avg_score or 0, 1),
        'recent_tests': recent_tests,
        'my_attempts': my_attempts,
        'is_teacher': user.is_teacher(),
    })
# ============================================================
# PROFIL
# ============================================================

@login_required(login_url='login')
def profile_view(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'update_info')

        # ============ MA'LUMOTLARNI YANGILASH ============
        if action == 'update_info':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            subject = request.POST.get('subject', '').strip()

            if not first_name or not last_name:
                messages.error(request, "Ism va familiya bo'sh bo'lmasligi kerak!")
                return redirect('profile')

            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.full_name = f"{first_name} {last_name}".strip()

            if request.user.is_teacher():
                request.user.subject = subject

            request.user.save()
            messages.success(request, "Profil ma'lumotlari yangilandi!")
            return redirect('profile')

        # ============ PAROLNI O'ZGARTIRISH ============
        elif action == 'change_password':
            current = request.POST.get('current_password', '')
            new_pass = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')

            if not request.user.check_password(current):
                messages.error(request, "Joriy parol noto'g'ri!")
                return redirect('profile')

            if len(new_pass) < 6:
                messages.error(request, "Yangi parol kamida 6 ta belgidan iborat bo'lishi kerak!")
                return redirect('profile')

            if new_pass != confirm:
                messages.error(request, "Yangi parollar mos kelmaydi!")
                return redirect('profile')

            if new_pass == current:
                messages.error(request, "Yangi parol joriy parol bilan bir xil bo'lmasligi kerak!")
                return redirect('profile')

            request.user.set_password(new_pass)
            request.user.save()
            update_session_auth_hash(request, request.user)  # sessiyani saqlash
            messages.success(request, "Parol muvaffaqiyatli o'zgartirildi!")
            return redirect('profile')

    return render(request, 'accounts/profile.html', {'user': request.user})
# ============================================================
# TEST YARATISH / TAHRIRLASH
# ============================================================

@teacher_approved_required
def create_or_edit_test(request, test_id=None):
    if not request.user.is_teacher():
        messages.error(request, "Faqat o'qituvchilar test yaratishi mumkin.")
        return redirect('dashboard')

    test = None
    if test_id:
        test = get_object_or_404(Test, id=test_id)
        if not test.is_owner(request.user):
            messages.error(request, "Bu testni tahrirlash huquqingiz yo'q.")
            
            return redirect('teacher_tests')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        subject_raw = request.POST.get('subject', '').strip()
        new_subject = request.POST.get('new_subject', '').strip()
        subject = new_subject if subject_raw == '__new__' else subject_raw

        duration = request.POST.get('duration_minutes', 45)
        test_type = request.POST.get('test_type', 'exam')
        target_grade = request.POST.get('target_grade', 'barcha')
        target_letter = request.POST.get('target_letter', 'barchasi')
        status = request.POST.get('status', 'draft')
        questions_json_raw = request.POST.get('questions_json', '[]')

        if not title:
            messages.error(request, "Test nomini kiriting!")
        elif not subject:
            messages.error(request, "Fan nomini tanlang yoki kiriting!")
        else:
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                duration = 45

            Subject.objects.get_or_create(name=subject[:100])

            try:
                questions_data = json.loads(questions_json_raw)
                if not isinstance(questions_data, list):
                    questions_data = []
            except json.JSONDecodeError:
                questions_data = []

            if test:
                test.title = title
                test.subject = subject
                test.duration_minutes = duration
                test.test_type = test_type
                test.target_grade = target_grade
                test.target_letter = target_letter
                test.status = status
                test.save()
                messages.success(request, "Test yangilandi!")
            else:
                test = Test.objects.create(
                    title=title,
                    subject=subject,
                    creator=request.user,
                    duration_minutes=duration,
                    test_type=test_type,
                    target_grade=target_grade,
                    target_letter=target_letter,
                    status=status,
                )
                messages.success(request, "Test yaratildi!")

            # ============================================================
            # SAVOLLARNI "UPSERT" qilish — o'chirmasdan!
            # ============================================================
            matched_q_ids = set()

            for idx, q_data in enumerate(questions_data, start=1):
                q_type = q_data.get('type', 'single')
                if q_type not in ('single', 'multiple', 'open'):
                    q_type = 'single'

                # Ball — 0 ni ham to'g'ri qabul qilish
                raw_points = q_data.get('points')
                if raw_points is None or raw_points == '':
                    points = 1.0
                else:
                    try:
                        points = float(raw_points)
                    except (TypeError, ValueError):
                        points = 1.0

                q_text = (q_data.get('text') or '').strip()
                correct_text = q_data.get('correct_text_answers', '') or ''

                # id bo'lsa — mavjudni yangilash; bo'lmasa — yangi yaratish
                q_id = q_data.get('id')
                question = None
                if q_id:
                    try:
                        question = Question.objects.get(id=int(q_id), test=test)
                        matched_q_ids.add(question.id)
                    except (Question.DoesNotExist, ValueError, TypeError):
                        question = None

                if question is None:
                    question = Question.objects.create(test=test)
                    matched_q_ids.add(question.id)

                question.text = q_text
                question.question_type = q_type
                question.points = points
                question.order = idx
                question.correct_text_answers = correct_text
                question.save()

                                # ============================================================
                # VARIANTLARNI "UPSERT" qilish — o'chirmasdan!
                # Bu o'quvchilarning eski javoblarini (selected_option) saqlaydi
                # ============================================================
                matched_opt_ids = set()

                if q_type in ('single', 'multiple'):
                    for opt_data in q_data.get('options', []):
                        opt_id = opt_data.get('id')
                        opt_text = (opt_data.get('text') or '').strip()
                        opt_correct = bool(opt_data.get('is_correct', False))

                        option = None
                        if opt_id:
                            try:
                                option = Option.objects.get(
                                    id=int(opt_id), question=question
                                )
                                matched_opt_ids.add(option.id)
                            except (Option.DoesNotExist, ValueError, TypeError):
                                option = None

                        if option is None:
                            option = Option.objects.create(question=question)
                            matched_opt_ids.add(option.id)

                        option.text = opt_text
                        option.is_correct = opt_correct
                        option.save()

                    # Payload da yo'q variantlarni o'chirish
                    for opt in question.options.all():
                        if opt.id not in matched_opt_ids:
                            opt.delete()
                else:
                    # Ochiq savol — eski variantlarni o'chirish
                    question.options.all().delete()

            # Payload da yo'q savollarni o'chirish
            for q in test.questions.all():
                if q.id not in matched_q_ids:
                    q.delete()
                        # ============================================================
            # TAHRIRLASHDAN KEYIN — qayta hisoblash / qayta urinish
            # ============================================================
            if test.test_type == 'exam':
                # Eski completed urinishlarni "stale" qilish
                stale_qs = TestAttempt.objects.filter(
                    test=test, status='completed'
                )
                stale_count = stale_qs.count()
                if stale_count > 0:
                    stale_qs.update(is_stale=True)
                    messages.info(
                        request,
                        f"⚠️ {stale_count} ta eski urinish endi qayta topshirishni talab qiladi "
                        f"(test tahrirlandi)."
                    )
            elif test.test_type in ('practice', 'survey', 'anonymous'):
                # Practice — qayta hisoblash
                if test.test_type == 'practice':
                    recalc_count = 0
                    for att in TestAttempt.objects.filter(test=test, status='completed'):
                        _recalculate_attempt(att)
                        recalc_count += 1
                    if recalc_count > 0:
                        messages.info(
                            request,
                            f"🔄 {recalc_count} ta urinish yangi savollar bo'yicha qayta hisoblandi."
                        )
                # survey/anonymous — hech narsa qilmaymiz

            return redirect('teacher_tests')

            return redirect('teacher_tests')

    # ============================================================
    # GET
    # ============================================================
    questions_json = []
    if test:
        for q in test.questions.all().order_by('order', 'id'):
            questions_json.append({
                'id': q.id,   # ← YANGI: id qo'shildi
                'text': q.text,
                'type': q.question_type,
                'points': q.points,
                'correct_text_answers': q.correct_text_answers or '',
                'options': [
                {'id': o.id, 'text': o.text, 'is_correct': o.is_correct}
                for o in q.options.all()
            ],
            })

    subjects = Subject.objects.all()

    return render(request, 'accounts/test_form.html', {
        'test': test,
        'questions_json': questions_json,
        'subjects': subjects,
    })

@teacher_approved_required
def close_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    if test.is_owner(request.user):
        test.status = 'closed'
        test.save()
        messages.success(request, "Test yopildi.")
    else:
        messages.error(request, "Ruxsat yo'q.")
    return redirect('teacher_tests')


@teacher_approved_required
def export_test_cloud_json(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    if not test.is_owner(request.user):
        return JsonResponse({'error': 'ruxsat yoq'}, status=403)

    data = {
        'id': test.id,
        'title': test.title,
        'subject': test.subject,
        'duration_minutes': test.duration_minutes,
        'test_type': test.test_type,
        'target_grade': test.target_grade,
        'target_letter': test.target_letter,
        'questions': [
            {
                'id': q.id,
                'text': q.text,
                'type': q.question_type,
                'points': q.points,
                'options': [
                    {'id': o.id, 'text': o.text, 'is_correct': o.is_correct}
                    for o in q.options.all()
                ],
            }
            for q in test.questions.all()
        ],
    }
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})


def download_sample_docx(request):
    return HttpResponse(
        "Namuna DOCX fayl — tez orada tayyor bo'ladi.",
        content_type='text/plain; charset=utf-8'
    )


# ============================================================
# TEST TOPSHIRISH
# ============================================================

@login_required(login_url='login')
def view_or_take_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    is_exam = (test.test_type == 'exam')

    # ============================================================
    # EXAM: faqat bir marta topshirish (stale bo'lmasa)
    # ============================================================
    if is_exam:
        already_completed = TestAttempt.objects.filter(
            student=request.user, test=test,
            status='completed', is_stale=False,
        ).exists()
        if already_completed:
            messages.error(request, "Bu nazorat ishini allaqachon topshirgansiz.")
            return redirect('student_results')

    # ============================================================
    # Mavjud ochiq urinish — muddati tugaganini tekshirish
    # ============================================================
    attempt = TestAttempt.objects.filter(
        student=request.user, test=test, status='in_progress'
    ).first()

    if attempt and attempt.remaining_seconds() <= 0:
        # Muddati tugagan — yopish va yangisini boshlash
        attempt.status = 'blocked'
        attempt.finished_at = timezone.now()
        attempt.save()
        attempt = None
        messages.warning(
            request,
            "Avvalgi urinish vaqti tugagan. Yangi urinish boshlang."
        )

    # ============================================================
    # Yangi urinish yaratish
    # ============================================================
    if not attempt and request.GET.get('start') == '1':
        attempt_number = TestAttempt.objects.filter(
            student=request.user, test=test
        ).count() + 1
        attempt = TestAttempt.objects.create(
            student=request.user,
            test=test,
            total_questions=test.questions.count(),
            attempt_number=attempt_number,
        )

    # ============================================================
    # Savollar
    # ============================================================
    questions_data = []
    if attempt:
        for q in test.questions.all().order_by('order', 'id'):
            questions_data.append({
                'id': q.id,
                'text': q.text,
                'type': q.question_type,
                'points': q.points,
                'options': [
                    {'id': o.id, 'text': o.text}
                    for o in q.options.all()
                ],
            })

    # ============================================================
    # Oldingi eng yaxshi natija (practice uchun)
    # ============================================================
    best_score = TestAttempt.objects.filter(
        student=request.user, test=test, status='completed'
    ).aggregate(best=Max('score'))['best']

    total_attempts = TestAttempt.objects.filter(
        student=request.user, test=test
    ).count()

    return render(request, 'accounts/take_test.html', {
        'test': test,
        'user': request.user,
        'attempt': attempt,
        'questions_data': questions_data,
        'is_exam': is_exam,
        'best_score': best_score,
        'total_attempts': total_attempts,
    })



@login_required(login_url='login')
def submit_test(request, attempt_id):
    attempt = get_object_or_404(TestAttempt, id=attempt_id)

    if attempt.student != request.user:
        return JsonResponse({'status': 'error', 'message': 'Ruxsat yo\'q'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST kerak'}, status=400)
    if attempt.status != 'in_progress':
        return JsonResponse({'status': 'error', 'message': 'Urinish yopilgan'}, status=400)

    is_survey = attempt.test.test_type in ('survey', 'anonymous')

    # ============================================================
    # SO'ROVNOMA / ANONIM — javoblarni saqlash, hisoblash YO'Q
    # ============================================================
    if is_survey:
        for question in attempt.test.questions.all():
            answer, _ = StudentAnswer.objects.get_or_create(
                attempt=attempt, question=question
            )
            if question.question_type == 'single':
                option_id = request.POST.get(f'question_{question.id}')
                if option_id:
                    try:
                        answer.selected_option = Option.objects.get(
                            id=option_id, question=question
                        )
                    except Option.DoesNotExist:
                        pass
            elif question.question_type == 'multiple':
                ids = request.POST.getlist(f'question_{question.id}')
                answer.selected_options.set(ids)
            elif question.question_type == 'open':
                answer.text_answer = request.POST.get(f'question_{question.id}', '').strip()
            answer.save()

        attempt.finished_at = timezone.now()
        attempt.status = 'completed'
        attempt.score = 0
        attempt.correct_count = 0
        attempt.earned_points = 0
        attempt.total_points = 0
        attempt.save()

        messages.success(request, "So'rovnoma qabul qilindi! Rahmat.")
        return redirect('student_results')

    # ============================================================
    # ODDIY TEST — ball hisoblash
    # ============================================================
    earned_points = 0.0
    total_points = 0.0
    correct_count = 0

    for question in attempt.test.questions.all().order_by('order', 'id'):
        q_points = float(question.points) if question.points is not None else 1.0
        total_points += q_points

        answer, _ = StudentAnswer.objects.get_or_create(
            attempt=attempt, question=question
        )
        is_correct = False

        if question.question_type == 'single':
            option_id = request.POST.get(f'question_{question.id}')
            if option_id:
                try:
                    opt = Option.objects.get(id=option_id, question=question)
                    answer.selected_option = opt
                    answer.save()
                    if opt.is_correct:
                        is_correct = True
                except Option.DoesNotExist:
                    answer.save()
            else:
                answer.save()

        elif question.question_type == 'multiple':
            ids = request.POST.getlist(f'question_{question.id}')
            answer.selected_options.set(ids)
            answer.save()
            cc = question.options.filter(is_correct=True).count()
            sc = answer.selected_options.filter(is_correct=True).count()
            sw = answer.selected_options.filter(is_correct=False).count()
            if cc > 0 and sc == cc and sw == 0:
                is_correct = True

        elif question.question_type == 'open':
            answer.text_answer = request.POST.get(f'question_{question.id}', '').strip()
            answer.save()
            if answer.text_answer and question.correct_text_answers:
                submitted_norm = _normalize_answer(answer.text_answer)
                valid_norms = [
                    _normalize_answer(a)
                    for a in question.correct_text_answers.split('|')
                    if a.strip()
                ]
                if submitted_norm and submitted_norm in valid_norms:
                    is_correct = True

        if is_correct:
            earned_points += q_points
            correct_count += 1

    score = (earned_points / total_points * 100) if total_points > 0 else 0.0

    attempt.finished_at = timezone.now()
    attempt.status = 'completed'
    attempt.correct_count = correct_count
    attempt.earned_points = round(earned_points, 2)
    attempt.total_points = round(total_points, 2)
    attempt.score = round(score, 1)
    attempt.save()

    messages.success(
        request,
        f"Test yakunlandi! Ball: {round(earned_points, 1)}/{round(total_points, 1)} ({attempt.score}%)"
    )
    return redirect('student_results')

def report_fullscreen_violation(request, attempt_id):
    attempt = get_object_or_404(TestAttempt, id=attempt_id)
    attempt.violation_count += 1
    attempt.save()
    return JsonResponse({'status': 'ok', 'violations': attempt.violation_count})


def send_excuse_message(request, attempt_id):
    attempt = get_object_or_404(TestAttempt, id=attempt_id)
    if request.method == 'POST':
        attempt.excuse_message = request.POST.get('message', '')
        attempt.save()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error', 'message': 'POST kerak'}, status=400)


def check_attempt_status(request, attempt_id):
    attempt = get_object_or_404(TestAttempt, id=attempt_id)
    return JsonResponse({
        'status': 'ok',
        'attempt_id': attempt.id,
        'state': attempt.status,
        'violations': attempt.violation_count,
        'remaining_seconds': attempt.remaining_seconds(),
    })


# ============================================================
# MONITORING
# ============================================================

@teacher_approved_required
def monitor_students(request, test_id):
    from collections import defaultdict

    test = get_object_or_404(Test, id=test_id)

    attempts = TestAttempt.objects.filter(test=test).select_related('student').order_by(
        'student__last_name', 'student__first_name', 'started_at'
    )

    # O'quvchi bo'yicha guruhlash
    students_map = defaultdict(list)
    for att in attempts:
        students_map[att.student_id].append(att)

    students_data = []
    for student_id, att_list in students_map.items():
        student = att_list[0].student

        # Har bir attempt uchun delta hisoblash
        enriched = []
        for i, att in enumerate(att_list):
            delta = None
            if i > 0 and att.status == 'completed' and att_list[i-1].status == 'completed':
                delta = round(att.score - att_list[i-1].score, 1)
            enriched.append({'att': att, 'delta': delta})

        students_data.append({
            'student': student,
            'attempts': enriched,
            'total_attempts': len(att_list),
        })

    # Familiya bo'yicha tartiblash (A-Z)
    students_data.sort(key=lambda x: (
        (x['student'].last_name or '').lower(),
        (x['student'].first_name or '').lower(),
    ))

    return render(request, 'accounts/monitor.html', {
        'test': test,
        'students_data': students_data,
    })


# ============================================================
# SHIKOYATLAR
# ============================================================

@login_required(login_url='login')
def submit_complaint(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    if request.method == 'POST':
        reason = (
            request.POST.get('reason', '').strip()
            or request.POST.get('message', '').strip()
        )
        Complaint.objects.create(
            student=request.user,
            question=question,
            reason=reason,
        )
        messages.success(request, "Shikoyat yuborildi.")
        return redirect('student_results')
    return JsonResponse({'status': 'error', 'message': 'POST kerak'}, status=400)



@teacher_approved_required
def review_complaint(request, complaint_id):
    complaint = get_object_or_404(
        Complaint.objects.select_related(
            'student', 'question', 'question__test'
        ).prefetch_related('question__options'),
        id=complaint_id
    )

    # Ruxsat tekshiruvi
    if not request.user.is_teacher() or complaint.question.test.creator != request.user:
        messages.error(request, "Bu shikoyatni ko'rish huquqingiz yo'q.")
        return redirect('dashboard')

    if request.method == 'POST':
        new_status = request.POST.get('status', 'reviewed')
        if new_status not in ('pending', 'reviewed', 'resolved', 'rejected'):
            new_status = 'reviewed'
        complaint.status = new_status
        complaint.teacher_comment = request.POST.get('teacher_comment', '').strip()
        complaint.save()
        messages.success(request, "Shikoyat yangilandi!")
        return redirect('teacher_complaints')

    # Ochiq savol uchun tayyor list
    valid_answers = []
    if complaint.question.correct_text_answers:
        valid_answers = [
            a.strip() for a in complaint.question.correct_text_answers.split('|')
            if a.strip()
        ]

    return render(request, 'accounts/complaint_review.html', {
        'complaint': complaint,
        'valid_answers': valid_answers,
    })
# ============================================================
# O'QITUVCHI SAHIFALARI
# ============================================================


@teacher_approved_required
def teacher_tests_view(request):
    if not request.user.is_teacher():
        messages.error(request, "Bu sahifa faqat o'qituvchilar uchun.")
        return redirect('dashboard')
    tests = Test.objects.filter(creator=request.user).order_by('-created_at')
    return render(request, 'accounts/teacher_tests.html', {'tests': tests})


@teacher_approved_required
def teacher_complaints_view(request):
    if not request.user.is_teacher():
        messages.error(request, "Bu sahifa faqat o'qituvchilar uchun.")
        return redirect('dashboard')

    status_filter = request.GET.get('status', 'all')

    base_qs = Complaint.objects.filter(
        question__test__creator=request.user
    ).select_related('question', 'question__test', 'student')

    qs = base_qs.order_by('-created_at')
    if status_filter in ('pending', 'reviewed', 'resolved', 'rejected'):
        qs = qs.filter(status=status_filter)

    counts = {
        'all': base_qs.count(),
        'pending': base_qs.filter(status='pending').count(),
        'reviewed': base_qs.filter(status='reviewed').count(),
        'resolved': base_qs.filter(status='resolved').count(),
        'rejected': base_qs.filter(status='rejected').count(),
    }

    return render(request, 'accounts/teacher_complaints.html', {
        'complaints': qs,
        'status_filter': status_filter,
        'counts': counts,
    })




@teacher_approved_required
def users_list_view(request):
    if not request.user.is_teacher():
        messages.error(request, "Bu sahifa faqat o'qituvchilar uchun.")
        return redirect('dashboard')

    role_filter = request.GET.get('role', 'all')
    search = request.GET.get('q', '').strip()

    qs = User.objects.all().order_by('last_name', 'first_name')

    if role_filter in ('student', 'teacher'):
        qs = qs.filter(role=role_filter)
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search) |
            Q(email__icontains=search)
        )

    counts = {
        'all': User.objects.count(),
        'student': User.objects.filter(role='student').count(),
        'teacher': User.objects.filter(role='teacher').count(),
    }

    return render(request, 'accounts/users_list.html', {
        'users': qs,
        'role_filter': role_filter,
        'search': search,
        'counts': counts,
    })

# ============================================================
# O'QUVCHI SAHIFALARI
# ============================================================

@login_required(login_url='login')
def student_rankings_view(request):
    students = User.objects.filter(role='student').annotate(
        avg_score=Avg('attempts__score'),
        attempts_count=Count('attempts'),
    ).filter(attempts_count__gt=0).order_by('-avg_score', '-attempts_count')[:50]

    rankings = _add_badges(list(students), len(students))

    return render(request, 'accounts/student_rankings.html', {
        'rankings': rankings,
        'total': len(students),
    })


@login_required(login_url='login')
def student_results_view(request):
    results = TestAttempt.objects.filter(
        student=request.user
    ).select_related('test').order_by('-started_at')
    return render(request, 'accounts/student_results.html', {'results': results})


# ============================================================
# API
# ============================================================

def api_overview(request):
    return JsonResponse({
        'api': 'v1',
        'status': 'ok',
        'user': request.user.username if request.user.is_authenticated else None,
    })

@teacher_approved_required
def monitor_list_view(request):
    """Barcha faol testlar ro'yxati — monitoring uchun"""
    if not request.user.is_teacher():
        messages.error(request, "Bu sahifa faqat o'qituvchilar uchun.")
        return redirect('dashboard')

    tests = Test.objects.filter(
        creator=request.user
    ).exclude(status='draft').order_by('-created_at')

    return render(request, 'accounts/monitor_list.html', {'tests': tests})



# ============================================================
# FAYL PARSER
# ============================================================


@teacher_approved_required
def parse_questions_file(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Fayl yuborilmagan'}, status=400)

    f = request.FILES['file']
    name = f.name.lower()
    content = f.read()

    try:
        if name.endswith('.txt'):
            text = content.decode('utf-8', errors='replace')
            qs = _parse_text(text)
        elif name.endswith('.csv'):
            qs = _parse_csv(content)
        elif name.endswith('.docx'):
            from docx import Document
            from io import BytesIO
            doc = Document(BytesIO(content))
            text = '\n'.join(p.text for p in doc.paragraphs)
            qs = _parse_text(text)
        elif name.endswith('.xlsx'):
            from openpyxl import load_workbook
            from io import BytesIO
            wb = load_workbook(BytesIO(content), data_only=True)
            ws = wb.active
            qs = _parse_xlsx(ws)
        else:
            return JsonResponse({'error': 'Fayl turi qo\'llab-quvvatlanmaydi. .txt/.csv/.docx/.xlsx'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Xatolik: {e}'}, status=400)

    return JsonResponse({'questions': qs, 'count': len(qs)})

def _normalize_answer(s):
    """Javobni bir xil formatga keltirish — ikkala tomon uchun ham.
    - strip
    - lowercase
    - bir nechta bo'shliqni bitta qilish
    """
    if s is None:
        return ''
    return ' '.join(str(s).strip().lower().split())


def _parse_text(text):
    import re
    questions = []
    blocks = re.split(r'\n\s*\n', text.strip())

    for block in blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) < 2:
            continue

        q_text = re.sub(r'^\d+[\.\)]\s*', '', lines[0])
        q_text = re.sub(r'^savol\s*\d*[\.\:]\s*', '', q_text, flags=re.I).strip()
        if not q_text:
            continue

        # 1) Ochiq savol tekshiruvi ("Qabul:" bilan)
        open_answers = None
        option_lines = []
        for line in lines[1:]:
            m_open = re.match(
                r'^(Qabul(?:\s+qilinadigan\s+javoblar?)?|Javoblar?|Answer|Answers)\s*[:\-]\s*(.+)$',
                line, re.IGNORECASE
            )
            if m_open:
                open_answers = m_open.group(2).strip()
                break
            option_lines.append(line)

        if open_answers is not None:
            parts = re.split(r'[,;]', open_answers)
            answers_clean = '|'.join(p.strip() for p in parts if p.strip())
            questions.append({
                'text': q_text, 'type': 'open', 'points': 1,
                'correct_text_answers': answers_clean, 'options': [],
            })
            continue

        # 2) Tanlov savoli — *A) format
        options = []
        correct_count = 0
        for line in option_lines:
            m = re.match(r'^(\*?)\s*([A-Da-dА-Да-д])\s*[\)\.\:]\s*(.+)$', line)
            if not m:
                continue
            star = m.group(1) == '*'
            opt_text = m.group(3).strip()
            is_correct = star
            if opt_text.endswith('*'):
                opt_text = opt_text[:-1].strip()
                is_correct = True
            if is_correct:
                correct_count += 1
            options.append({'text': opt_text, 'is_correct': is_correct})

        if len(options) < 2:
            continue

        if correct_count == 1:
            q_type = 'single'
        elif correct_count >= 2:
            q_type = 'multiple'
        else:
            # 0 ta * → yagona tanlov, lekin to'g'ri javob belgilanmagan
            q_type = 'single'

        questions.append({
            'text': q_text, 'type': q_type, 'points': 1,
            'correct_text_answers': '', 'options': options,
        })

    return questions


def _parse_csv(content):
    import csv, re
    from io import StringIO
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('cp1251', errors='replace')

    rows = list(csv.reader(StringIO(text)))
    questions = []

    for i, row in enumerate(rows):
        if not row or len(row) < 2:
            continue
        if i == 0 and row[0].strip().lower() in ('question', 'savol', 'савол'):
            continue

        q_text = row[0].strip()
        if not q_text:
            continue

        cells = [c.strip() for c in row[1:]]
        last_cell = cells[-1] if cells else ''

        # Ochiq savol — oxirgi katakda "Qabul:"
        m_open = re.match(
            r'^(Qabul(?:\s+qilinadigan\s+javoblar?)?|Javoblar?|Answer|Answers)\s*[:\-]\s*(.+)$',
            last_cell, re.IGNORECASE
        )
        if m_open:
            parts = re.split(r'[,;]', m_open.group(2))
            answers_clean = '|'.join(p.strip() for p in parts if p.strip())
            questions.append({
                'text': q_text, 'type': 'open', 'points': 1,
                'correct_text_answers': answers_clean, 'options': [],
            })
            continue

        # * prefiks bor-yo'qligini tekshirish
        any_star = any(c.startswith('*') or c.endswith('*') for c in cells if c)
        correct_indicator = ''
        option_cells = cells

        # * yo'q bo'lsa, oxirgi ustunni "correct answer" deb tekshirish
        if not any_star and last_cell and re.match(r'^[A-Da-d][,\s]*([A-Da-d][,\s]*)*$', last_cell):
            correct_indicator = last_cell.upper()
            option_cells = cells[:-1]

        options = []
        for cell in option_cells:
            if not cell:
                continue
            is_correct = False
            if cell.startswith('*'):
                is_correct = True
                cell = cell[1:].strip()
            elif cell.endswith('*'):
                is_correct = True
                cell = cell[:-1].strip()
            options.append({'text': cell, 'is_correct': is_correct})

        if correct_indicator:
            for letter in re.findall(r'[A-D]', correct_indicator):
                idx = ord(letter) - ord('A')
                if 0 <= idx < len(options):
                    options[idx]['is_correct'] = True

        if len(options) < 2:
            continue

        cc = sum(1 for o in options if o['is_correct'])
        q_type = 'multiple' if cc >= 2 else 'single'

        questions.append({
            'text': q_text, 'type': q_type, 'points': 1,
            'correct_text_answers': '', 'options': options,
        })

    return questions


def _parse_xlsx(ws):
    import re
    questions = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        if not row or not row[0]:
            continue
        q_text = str(row[0]).strip()
        if not q_text:
            continue

        cells = [str(c).strip() if c is not None else '' for c in row[1:]]
        last_cell = cells[-1] if cells else ''

        m_open = re.match(
            r'^(Qabul(?:\s+qilinadigan\s+javoblar?)?|Javoblar?|Answer|Answers)\s*[:\-]\s*(.+)$',
            last_cell, re.IGNORECASE
        )
        if m_open:
            parts = re.split(r'[,;]', m_open.group(2))
            answers_clean = '|'.join(p.strip() for p in parts if p.strip())
            questions.append({
                'text': q_text, 'type': 'open', 'points': 1,
                'correct_text_answers': answers_clean, 'options': [],
            })
            continue

        any_star = any(c.startswith('*') or c.endswith('*') for c in cells if c)
        correct_indicator = ''
        option_cells = cells

        if not any_star and last_cell and re.match(r'^[A-Da-d][,\s]*([A-Da-d][,\s]*)*$', last_cell):
            correct_indicator = last_cell.upper()
            option_cells = cells[:-1]

        options = []
        for cell in option_cells:
            if not cell:
                continue
            is_correct = False
            if cell.startswith('*'):
                is_correct = True
                cell = cell[1:].strip()
            elif cell.endswith('*'):
                is_correct = True
                cell = cell[:-1].strip()
            options.append({'text': cell, 'is_correct': is_correct})

        if correct_indicator:
            for letter in re.findall(r'[A-D]', correct_indicator):
                idx = ord(letter) - ord('A')
                if 0 <= idx < len(options):
                    options[idx]['is_correct'] = True

        if len(options) < 2:
            continue

        cc = sum(1 for o in options if o['is_correct'])
        q_type = 'multiple' if cc >= 2 else 'single'

        questions.append({
            'text': q_text, 'type': q_type, 'points': 1,
            'correct_text_answers': '', 'options': options,
        })

    return questions



def _add_badges(items, total):
    """Har bir elementga rank va badge ma'lumotlarini qo'shadi"""
    result = []
    for i, item in enumerate(items, start=1):
        pct = (i / total * 100) if total else 100
        if i <= 3:
            badge = {'cls': 'gold', 'medal': '🥇' if i == 1 else ('🥈' if i == 2 else '🥉')}
        elif i <= 10:
            badge = {'cls': 'silver', 'medal': f'#{i}'}
        elif pct <= 40:
            badge = {'cls': 'green', 'medal': f'#{i}'}
        elif pct <= 70:
            badge = {'cls': 'blue', 'medal': f'#{i}'}
        else:
            badge = {'cls': 'yellow', 'medal': f'#{i}'}
        result.append({'obj': item, 'rank': i, 'badge': badge})
    return result


@login_required(login_url='login')
def teacher_rankings_view(request):
    teachers = User.objects.filter(role='teacher').annotate(
        total_tests=Count('created_tests', distinct=True),
        total_attempts=Count('created_tests__attempts', distinct=True),
    ).filter(total_tests__gt=0).order_by('-total_attempts', '-total_tests')[:50]

    rankings = _add_badges(list(teachers), len(teachers))

    return render(request, 'accounts/teacher_rankings.html', {
        'rankings': rankings,
        'total': len(teachers),
    })


@teacher_approved_required
def parse_text_questions(request):
    """Matnni serverda parse qilish — fayl bilan bir xil sifatda"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST kerak'}, status=400)

    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'Matn bo\'sh'}, status=400)

    try:
        qs = _parse_text(text)
    except Exception as e:
        return JsonResponse({'error': f'Xatolik: {e}'}, status=400)

    return JsonResponse({'questions': qs, 'count': len(qs)})



@teacher_approved_required
def export_test_as_text(request, test_id):
    """Testni matn (.txt) formatida yuklab olish.
    Format xuddi 'Matndan' import bilan bir xil — qayta import qilsa bo'ladi."""
    test = get_object_or_404(Test, id=test_id)

    if not test.is_owner(request.user):
        messages.error(request, "Ruxsat yo'q.")
        return redirect('teacher_tests')

    lines = []

    # Test sarlavhasi (comment sifatida — import qilganda o'tkazib yuboriladi)
    lines.append(f"# Test: {test.title}")
    lines.append(f"# Fan: {test.subject}")
    lines.append(f"# Vaqt: {test.duration_minutes} daqiqa")
    lines.append("")

    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

    for idx, q in enumerate(test.questions.all().order_by('order', 'id'), start=1):
        lines.append(f"{idx}. {q.text}")

        if q.question_type == 'open':
            if q.correct_text_answers:
                answers = [
                    a.strip()
                    for a in q.correct_text_answers.split('|')
                    if a.strip()
                ]
                lines.append(f"Qabul: {', '.join(answers)}")
        else:
            for i, opt in enumerate(q.options.all()):
                letter = letters[i] if i < len(letters) else str(i + 1)
                prefix = '*' if opt.is_correct else ''
                lines.append(f"{prefix}{letter}) {opt.text}")

        lines.append("")  # savollar orasida bo'sh qator

    content = '\n'.join(lines)

    # Xavfsiz fayl nomi
    safe_title = ''.join(
        c for c in test.title if c.isalnum() or c in ' -_'
    ).strip()[:50] or f'test_{test.id}'

    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{safe_title}.txt"'
    return response



@login_required(login_url='login')
def file_complaint(request, attempt_id):
    """O'quvchi test yakunlangandan keyin shikoyat yuboradi"""
    attempt = get_object_or_404(TestAttempt, id=attempt_id)

    if attempt.student != request.user:
        messages.error(request, "Ruxsat yo'q.")
        return redirect('dashboard')

    if attempt.status != 'completed':
        messages.error(request, "Avval testni yakunlang.")
        return redirect('student_results')

    questions = attempt.test.questions.all().order_by('order', 'id')

    if request.method == 'POST':
        question_id = request.POST.get('question_id', '').strip()
        reason = request.POST.get('reason', '').strip()

        if not question_id:
            messages.error(request, "Savolni tanlang!")
        elif not reason:
            messages.error(request, "Shikoyat sababini yozing!")
        else:
            question = get_object_or_404(Question, id=question_id, test=attempt.test)
            Complaint.objects.create(
                student=request.user,
                question=question,
                reason=reason,
            )
            messages.success(request, "Shikoyat muvaffaqiyatli yuborildi!")
            return redirect('student_results')

    return render(request, 'accounts/file_complaint.html', {
        'attempt': attempt,
        'questions': questions,
    })



@teacher_approved_required
def export_results_excel(request, test_id):
    """Test natijalarini Excel (.xlsx) sifatida yuklab olish"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO

    test = get_object_or_404(Test, id=test_id)

    if not test.is_owner(request.user):
        messages.error(request, "Ruxsat yo'q.")
        return redirect('teacher_tests')

    questions = list(test.questions.all().order_by('order', 'id'))

    # Faqat yakunlangan urinishlar
    attempts = list(
        TestAttempt.objects.filter(test=test, status='completed')
        .select_related('student')
        .prefetch_related(
            'answers__question',
            'answers__selected_option',
            'answers__selected_options',
        )
    )

    # Familiya + Ism bo'yicha tartiblash (A-Z)
    attempts.sort(key=lambda a: (
        (a.student.last_name or '').lower(),
        (a.student.first_name or '').lower(),
    ))

    wb = Workbook()
    ws = wb.active
    ws.title = 'Natijalar'

    # ============================================================
    # HEADER
    # ============================================================
    headers = ['#', 'Familiya Ism', 'Rol']
    for i, q in enumerate(questions, start=1):
        headers.append(f'{i}-savol')
    headers += ['Umumiy ball', "To'g'ri javoblar", 'Foiz (%)']

    ws.append(headers)

    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill('solid', fgColor='3B82F6')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC'),
    )

    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # ============================================================
    # ROWS
    # ============================================================
    for idx, attempt in enumerate(attempts, start=1):
        answers_map = {a.question_id: a for a in attempt.answers.all()}

        last = (attempt.student.last_name or '').strip()
        first = (attempt.student.first_name or '').strip()
        full_name = f"{last} {first}".strip() or attempt.student.username

        row = [
            idx,
            full_name,
            "O'qituvchi" if attempt.student.is_teacher() else "O'quvchi",
        ]

        for q in questions:
            ans = answers_map.get(q.id)
            answer_text = '—'

            if ans:
                if q.question_type == 'single' and ans.selected_option:
                    answer_text = ans.selected_option.text
                elif q.question_type == 'multiple':
                    opts = list(ans.selected_options.all())
                    answer_text = ', '.join(o.text for o in opts) if opts else '—'
                elif q.question_type == 'open':
                    answer_text = ans.text_answer or '—'
                else:
                    answer_text = '—'

            row.append(answer_text)

        row += [
            attempt.earned_points or 0,
            attempt.correct_count or 0,
            attempt.score or 0,
        ]
        ws.append(row)

        # Border har bir katakka
        for cell in ws[ws.max_row]:
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center', wrap_text=(cell.column > 3))

    # ============================================================
    # COLUMN WIDTHS
    # ============================================================
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 28
    ws.column_dimensions['C'].width = 14
    for i in range(4, 4 + len(questions)):
        ws.column_dimensions[get_column_letter(i)].width = 22
    ws.column_dimensions[get_column_letter(4 + len(questions))].width = 14
    ws.column_dimensions[get_column_letter(5 + len(questions))].width = 16
    ws.column_dimensions[get_column_letter(6 + len(questions))].width = 12

    # Header row balandligi
    ws.row_dimensions[1].height = 30

    # Freeze top row
    ws.freeze_panes = 'A2'

    # ============================================================
    # RESPONSE
    # ============================================================
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_title = ''.join(
        c for c in test.title if c.isalnum() or c in ' -_'
    ).strip()[:50] or f'test_{test.id}'

    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{safe_title}_natijalar.xlsx"'
    return response



def _recalculate_attempt(attempt):
    """Mavjud urinishni yangi savollar bo'yicha qayta hisoblash.
    Yangi qo'shilgan savollarga javob yo'q → 0 ball, lekin total ga qo'shiladi."""
    test = attempt.test
    total_points = 0.0
    earned_points = 0.0
    correct_count = 0

    for q in test.questions.all():
        q_points = float(q.points) if q.points is not None else 1.0
        total_points += q_points

        try:
            answer = StudentAnswer.objects.get(attempt=attempt, question=q)
        except StudentAnswer.DoesNotExist:
            continue  # javob yo'q → 0 ball

        is_correct = False

        if q.question_type == 'single':
            if answer.selected_option and answer.selected_option.is_correct:
                is_correct = True
        elif q.question_type == 'multiple':
            cc = q.options.filter(is_correct=True).count()
            sc = answer.selected_options.filter(is_correct=True).count()
            sw = answer.selected_options.filter(is_correct=False).count()
            if cc > 0 and sc == cc and sw == 0:
                is_correct = True
        elif q.question_type == 'open':
            if answer.text_answer and q.correct_text_answers:
                submitted_norm = _normalize_answer(answer.text_answer)
                valid_norms = [
                    _normalize_answer(a)
                    for a in q.correct_text_answers.split('|')
                    if a.strip()
                ]
                if submitted_norm and submitted_norm in valid_norms:
                    is_correct = True

        if is_correct:
            earned_points += q_points
            correct_count += 1

    attempt.earned_points = round(earned_points, 2)
    attempt.total_points = round(total_points, 2)
    attempt.correct_count = correct_count
    attemattempt.score = round((earned_points / total_points * 100) if total_points else 0, 1)
    attempt.is_stale = False
    attempt.save()
# ============================================================
# ADMIN PANEL
# ============================================================

def _superuser_required(view_func):
    """Faqat superuser"""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_superuser:
            messages.error(request, "Bu sahifa faqat administrator uchun.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


@_superuser_required
def admin_panel_view(request):
    """Admin panel — umumiy ko'rinish"""
    pending_count = User.objects.filter(
        role='teacher', is_approved=False, is_active=True
    ).count()
    approved_teachers = User.objects.filter(
        role='teacher', is_approved=True, is_active=True
    ).count()
    total_students = User.objects.filter(role='student').count()
    total_tests = Test.objects.count()
    total_attempts = TestAttempt.objects.count()
    total_complaints = Complaint.objects.count()

    return render(request, 'accounts/admin_panel.html', {
        'pending_count': pending_count,
        'approved_teachers': approved_teachers,
        'total_students': total_students,
        'total_tests': total_tests,
        'total_attempts': total_attempts,
        'total_complaints': total_complaints,
    })


@_superuser_required
def admin_teachers_view(request):
    """O'qituvchilar ro'yxati — tasdiqlash uchun"""
    pending = User.objects.filter(
        role='teacher', is_approved=False, is_active=True
    ).order_by('-date_joined')

    approved = User.objects.filter(
        role='teacher', is_approved=True, is_active=True
    ).order_by('-date_joined')

    rejected = User.objects.filter(
        role='teacher', is_active=False
    ).order_by('-date_joined')

    return render(request, 'accounts/admin_teachers.html', {
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
    })


@_superuser_required
def admin_approve_teacher(request, user_id):
    """O'qituvchini tasdiqlash"""
    if request.method != 'POST':
        return redirect('admin_teachers')

    user = get_object_or_404(User, id=user_id, role='teacher')
    user.is_approved = True
    user.is_active = True
    user.save(update_fields=['is_approved', 'is_active'])
    messages.success(request, f"{user.get_display_name()} tasdiqlandi.")
    return redirect('admin_teachers')


@_superuser_required
def admin_reject_teacher(request, user_id):
    """O'qituvchini rad etish (soft delete)"""
    if request.method != 'POST':
        return redirect('admin_teachers')

    user = get_object_or_404(User, id=user_id, role='teacher')
    user.is_approved = False
    user.is_active = False
    user.save(update_fields=['is_approved', 'is_active'])
    messages.warning(request, f"{user.get_display_name()} rad etildi.")
    return redirect('admin_teachers')


@_superuser_required
def admin_reset_results(request):
    """Barcha natijalarni o'chirish — testlar qoladi"""
    if request.method == 'POST':
        attempts_count = TestAttempt.objects.count()
        answers_count = StudentAnswer.objects.count()

        # CASCADE: TestAttempt o'chsa, StudentAnswer ham o'chadi
        TestAttempt.objects.all().delete()

        # Chempion hisoblagichlarni nolga tushirish
        User.objects.filter(role='student').update(monthly_champion_count=0)

        messages.success(
            request,
            f"Tozalandi: {attempts_count} ta urinish, {answers_count} ta javob. "
            f"Testlar va savollar saqlanib qoldi."
        )
        return redirect('admin_panel')

    # GET — tasdiqlash sahifasi
    attempts_count = TestAttempt.objects.count()
    answers_count = StudentAnswer.objects.count()
    tests_count = Test.objects.count()
    complaints_count = Complaint.objects.count()

    return render(request, 'accounts/admin_reset_confirm.html', {
        'attempts_count': attempts_count,
        'answers_count': answers_count,
        'tests_count': tests_count,
        'complaints_count': complaints_count,
    })
