from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.shortcuts import render
import json
import openai

# Initialize OpenAI client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

@csrf_exempt
def chat_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user_message = data.get('message', '')

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": user_message}],
                max_tokens=500,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
            return JsonResponse({'response': reply})
        except Exception as e:
            return JsonResponse({'response': f"Error: {str(e)}"}, status=500)

def chat_view(request):
    return render(request, 'chat_window.html')
