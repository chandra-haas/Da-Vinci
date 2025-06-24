import threading
import time
import speech_recognition as sr

class VoiceListener:
    def __init__(self, intent_callback, listen_duration=2):
        self.recognizer = sr.Recognizer()
        self.mic = sr.Microphone()
        self.listen_duration = listen_duration  # seconds
        self.running = False
        self.thread = None
        self.intent_callback = intent_callback  # function to call when intent detected

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._listen_loop)
            self.thread.daemon = True
            self.thread.start()
            print("VoiceListener started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        print("VoiceListener stopped.")

    def _listen_loop(self):
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source)
            print("Listening for intent...")
            while self.running:
                try:
                    audio = self.recognizer.listen(source, phrase_time_limit=self.listen_duration)
                    transcript = self.recognizer.recognize_google(audio)
                    print(f"Transcript: {transcript}")
                    if self.detect_intent(transcript):
                        print("Intent detected! Triggering callback.")
                        self.intent_callback(transcript)
                except sr.UnknownValueError:
                    pass  # No speech detected
                except Exception as e:
                    print(f"VoiceListener error: {e}")
                time.sleep(0.1)  # small delay to avoid busy loop

    def detect_intent(self, transcript):
        # Placeholder: Replace this with ML/NLP-based intent detection
        # Simple rule: if 'da vinci' is mentioned, return True
        return "da vinci" in transcript.lower() or "hey da vinci" in transcript.lower()

# Example callback function
def handle_intent(transcript):
    print(f"Handling intent: {transcript}")
    # Here you would trigger your assistant logic

if __name__ == "__main__":
    listener = VoiceListener(handle_intent)
    try:
        listener.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()