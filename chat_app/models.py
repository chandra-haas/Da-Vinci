from django.db import models

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