from django.contrib import admin
from django.urls import path, include
urlpatterns = [path('admin/', admin.site.urls), path('', include('accounts.urls'))]
from django.urls import path
from . import views

urlpatterns = [
    # Asosiy linklar (oxirida / bilan)
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    
    # Agar kimdir .html bilan yozsa ham avtomatik ochilishi uchun:
    path('signup.html', views.signup_view),
    path('login.html', views.login_view),
]
