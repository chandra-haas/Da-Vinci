import os
import json
import joblib
import openai
from django.conf import settings
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

# Setup
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")
DATA_PATH = os.path.join(os.path.dirname(__file__), "intent_examples.json")

ALLOWED_INTENTS = {
    "date", "time", "day", "web_search", "calculator", "ai",
    "gmail.compose", "gmail.read",
    "google_meet.schedule",
    "google_tasks.add", "google_tasks.read",
    "google_drive.upload", "google_drive.search",
    "outlook_mail.compose", "outlook_mail.read",
    "microsoft_teams.schedule",
    "microsoft_todo.add", "microsoft_todo.read",
    "one_drive.upload", "one_drive.search",
    "notepad.open"
}

# Load model if exists
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    model = None


def ml_predict(message):
    if model is None:
        return "ai", 0.0
    try:
        proba = model.predict_proba([message])[0]
        intent = model.classes_[proba.argmax()]
        confidence = proba.max()
        return intent, confidence
    except Exception as e:
        print(f"[ML] Error: {e}")
        return "ai", 0.0


def gpt_predict(message):
    prompt = [
        {
            "role": "system",
            "content": (
                "You are a strict intent classifier. Choose only one of the following:\n"
                + ", ".join(sorted(ALLOWED_INTENTS)) +
                "\nRespond with only the label like `gmail.compose`."
            )
        },
        {"role": "user", "content": message}
    ]
    try:
        result = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=prompt,
            max_tokens=10,
            temperature=0
        )
        response = result.choices[0].message.content.strip().lower()
        return response if response in ALLOWED_INTENTS else "ai"
    except Exception as e:
        print(f"[GPT] Error: {e}")
        return "ai"


def log_and_retrain(message, intent):
    # Log new data
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data.append({"text": message, "intent": intent})
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[INFO] Added to training data: {message} → {intent}")

    # Retrain model
    X = [item["text"] for item in data]
    y = [item["intent"] for item in data]

    if len(X) < 3:
        print("[WARNING] Not enough data to train. Skipping.")
        return

    pipeline = Pipeline([
        ('vectorizer', TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ('classifier', LogisticRegression(max_iter=1000))
    ])

    try:
        if len(X) >= 5:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            pipeline.fit(X_train, y_train)
            print("[INFO] Retrained model with evaluation:")
            print(classification_report(y_test, pipeline.predict(X_test)))
        else:
            pipeline.fit(X, y)
            print("[INFO] Retrained model on full dataset (too small to split).")

        joblib.dump(pipeline, MODEL_PATH)
        global model
        model = pipeline
        print(f"[INFO] Saved updated model to: {MODEL_PATH}")
    except Exception as e:
        print(f"[ERROR] Retraining failed: {e}")


def classify_intent(message):
    print(f"[🧠 ML+GPT Classifier] User Message: {message}")

    ml_intent, ml_conf = ml_predict(message)
    gpt_intent = gpt_predict(message)

    print(f"\n🤖 ML Prediction: {ml_intent} (confidence: {round(ml_conf, 2)})")
    print(f"🤖 GPT Prediction: {gpt_intent}\n")

    print("Which prediction is correct?")
    print(f"[1] {ml_intent}")
    print(f"[2] {gpt_intent}")
    print("[3] Enter a different intent manually")
    choice = input("Your choice (1/2/3): ")

    if choice == "1":
        correct_intent = ml_intent
    elif choice == "2":
        correct_intent = gpt_intent
    else:
        correct_intent = input("Enter the correct intent: ").strip()

    log_and_retrain(message, correct_intent)
    return correct_intent