from django.urls import path
from .views import chat_view, chat_api

urlpatterns = [
    path('', chat_view, name='chat_view'),       # chat page at /chat/
    path('api/chat/', chat_api, name='chat_api'), # API at /chat/api/chat/
]
