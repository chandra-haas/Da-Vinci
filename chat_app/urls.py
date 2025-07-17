from django.urls import path
from . import views
from .app_services.google import google_auth_views
from .app_services.microsoft import microsoft_auth_views

urlpatterns = [
    path('', views.chat_view, name='chat_view'),                      # Chat page at /
    path('api/chat/', views.chat_api, name='chat_api'),              # API endpoint
    path("auth/google/login/", google_auth_views.google_login, name="google_login"),
    path("auth/google/callback/", google_auth_views.google_auth_callback, name="google_callback"),
    path("auth/microsoft/login/", microsoft_auth_views.microsoft_login, name="microsoft_login"),
    path("auth/microsoft/callback/", microsoft_auth_views.microsoft_auth_callback, name="microsoft_callback"),
]
