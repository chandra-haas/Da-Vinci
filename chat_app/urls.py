from django.urls import path
from . import views
from . import google_auth_views  # Import views directly (so you can access all view functions)

urlpatterns = [
    path('', views.chat_view, name='chat_view'),                      # Chat page at /
    path('api/chat/', views.chat_api, name='chat_api'),              # API endpoint
    path("auth/google/login/", google_auth_views.google_login, name="google_login"),
    path("auth/google/callback/", google_auth_views.google_auth_callback, name="google_callback"),
]
