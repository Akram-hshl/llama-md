import speech_recognition as sr

r = sr.Recognizer()

while True:
    try:
        with sr.Microphone() as source:  # Fixed function name
            print("Say something, good")
            
            r.adjust_for_ambient_noise(source, duration=1)  # Reduce background noise
            audio = r.listen(source)  # Fixed method name
            
            text = r.recognize_google(audio)
            text = text.lower()

            print(f"Recognized text: {text}")

    except Exception as e:  # More specific exception handling
        print(f"Error: {e}")  # Print the actual error for debugging
        r = sr.Recognizer()  # Reinitialize recognizer
        continue  # Continue the loop
