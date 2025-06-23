from django.db import models
<<<<<<< HEAD
from django.contrib.auth.models import User
from django.utils import timezone

class MainMemory(models.Model):
    """
    Global memory; master record of all chat sessions for a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"MainMemory for {self.user.username if self.user else 'Anonymous'}"

class ChatSession(models.Model):
    """
    Represents a single chat session.
    """
    main_memory = models.ForeignKey(MainMemory, on_delete=models.CASCADE, related_name='chat_sessions')
    session_name = models.CharField(max_length=255, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)

    # For future extensibility
    misc_memory = models.JSONField(default=dict, blank=True)

    # ↓↓↓ Add these two fields to store in-progress actions for this session ↓↓↓
    pending_intent = models.CharField(max_length=100, null=True, blank=True)
    pending_data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.session_name or f"Session {self.id}"

class SubMemory(models.Model):
    """
    Highest-priority session memory (user preferences).
    """
    chat_session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='sub_memory')
    preferences = models.JSONField(default=dict, blank=True)  # Store preferences as JSON

class SessionMemory(models.Model):
    """
    Fact bank for the session; all relevant facts/questions/answers.
    """
    chat_session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='session_memory')
    facts = models.JSONField(default=dict, blank=True)  # Store facts as JSON

class CacheMemory(models.Model):
    """
    Active working memory for the session.
    """
    chat_session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='cache_memory')
    cache = models.JSONField(default=dict, blank=True)  # Store current context as JSON

class Message(models.Model):
    """
    Stores individual messages (chat history) within a session.
    """
    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20)  # 'user' or 'assistant'
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
=======

class ChatSession(models.Model):
    session_id = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20)  # 'user' or 'assistant'
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

class MemoryFact(models.Model):
    chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='facts')
    key = models.CharField(max_length=100)
    value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
>>>>>>> c88ac103dbcd299eccaf81ac54a241438167ebfc
