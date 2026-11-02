from django.urls import path
from . import views

urlpatterns = [
    # Asosiy sahifa va autentifikatsiya
    path('', views.dashboard_view, name='dashboard'),
    path('dashboard.html', views.dashboard_view),
    
    path('login/', views.login_view, name='login'),
    path('login.html', views.login_view),
    
    path('signup/', views.signup_view, name='signup'),
    path('signup.html', views.signup_view),
    
    path('auth/google/login/', views.google_login_start, name='google_login'),
    path('auth/google/callback/', views.google_login_callback, name='google_callback'),
    
    path('profile/', views.profile_view, name='profile'),
    path('profile.html', views.profile_view),
    
    path('logout/', views.logout_view, name='logout'),
    
    # Testlar va jarayonlar
    path('test/sample-docx/', views.download_sample_docx, name='sample_docx'),
    path('test/create/', views.create_or_edit_test, name='test_create'),
    path('test/<int:test_id>/edit/', views.create_or_edit_test, name='test_edit'),
    path('test_form.html', views.create_or_edit_test),  # Agar to'g'ridan-to'g'ri .html yozilsa
    
    path('test/<int:test_id>/cloud-json/', views.export_test_cloud_json, name='test_cloud_json'),
    path('test/<int:test_id>/close/', views.close_test, name='test_close'),
    path('test/<int:test_id>/take/', views.view_or_take_test, name='test_view'),
    
    path('attempt/<int:attempt_id>/submit/', views.submit_test, name='submit_test'),
    path('attempt/<int:attempt_id>/violation/', views.report_fullscreen_violation, name='report_violation'),
    path('attempt/<int:attempt_id>/excuse/', views.send_excuse_message, name='send_excuse'),
    path('attempt/<int:attempt_id>/status/', views.check_attempt_status, name='attempt_status'),
    
    path('test/<int:test_id>/monitor/', views.monitor_students, name='monitor_students'),
    path('monitor.html', views.monitor_students),
    
    path('question/<int:question_id>/complaint/', views.submit_complaint, name='submit_complaint'),
    path('complaint/<int:complaint_id>/review/', views.review_complaint, name='review_complaint'),
    path('complaint_review.html', views.review_complaint),
    
    # O'qituvchi va o'quvchi bo'limlari
    path('teacher/tests/', views.teacher_tests_view, name='teacher_tests'),
    path('teacher_tests.html', views.teacher_tests_view),
    
    path('teacher/complaints/', views.teacher_complaints_view, name='teacher_complaints'),
    path('teacher_complaints.html', views.teacher_complaints_view),
    
    path('teacher/students/', views.students_list_view, name='students_list'),
    path('students_list.html', views.students_list_view),
    
    path('student/rankings/', views.student_rankings_view, name='student_rankings'),
    path('student_rankings.html', views.student_rankings_view),
    
    path('student/results/', views.student_results_view, name='student_results'),
    path('student_results.html', views.student_results_view),
    
    path('api/v1/me/', views.api_overview, name='api_overview'),
]
