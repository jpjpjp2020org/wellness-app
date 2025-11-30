from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('ai-assistant/', views.ai_assistant, name='ai_assistant'),
    path('chat/', views.chat_with_ai, name='chat_with_ai'),
    path('ai-assistant/diet/', views.diet_analytics_playground, name='diet_analytics_playground'),
    path('ai-assistant/chat/', views.chat_with_ai, name='chat_with_ai'),
    path('ai-assistant/get_chat_history/', views.get_chat_history, name='get_chat_history'),
]

