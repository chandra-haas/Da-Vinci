import json
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

def load_data(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    X = [item['text'] for item in data]
    y = [item['intent'] for item in data]
    return X, y

def train_and_save_model(data_path, model_path):
    print(f"[INFO] Loading data from: {data_path}")
    X, y = load_data(data_path)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = Pipeline([
        ('vectorizer', TfidfVectorizer(ngram_range=(1,2), max_features=5000)),
        ('classifier', LogisticRegression(max_iter=1000))
    ])

    print("[INFO] Training model...")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print("[INFO] Evaluation Report:\n")
    print(classification_report(y_test, y_pred))

    joblib.dump(model, model_path)
    print(f"[INFO] Model saved to: {model_path}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train intent classifier")
    parser.add_argument('--input', type=str, required=True, help='Path to intent data (JSON)')
    parser.add_argument('--output', type=str, default='model.pkl', help='Path to save model')
    
    args = parser.parse_args()
    train_and_save_model(args.input, args.output)