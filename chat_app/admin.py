<<<<<<< HEAD
from django.contrib import admin
from .models import MainMemory, ChatSession, SubMemory, SessionMemory, CacheMemory, Message

@admin.register(MainMemory)
class MainMemoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created_at')
    search_fields = ('user__username',)

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'main_memory', 'session_name', 'created_at', 'last_accessed')
    search_fields = ('session_name', 'main_memory__user__username')
    list_filter = ('created_at',)

@admin.register(SubMemory)
class SubMemoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_session')
    search_fields = ('chat_session__session_name',)

@admin.register(SessionMemory)
class SessionMemoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_session')
    search_fields = ('chat_session__session_name',)

@admin.register(CacheMemory)
class CacheMemoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_session')
    search_fields = ('chat_session__session_name',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_session', 'sender', 'timestamp')
    search_fields = ('chat_session__session_name', 'sender', 'content')
    list_filter = ('sender', 'timestamp')
=======
from django.contrib import admin
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
