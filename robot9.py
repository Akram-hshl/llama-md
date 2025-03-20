from groq import Groq
import speech_recognition as sr
import gtts
import io
import base64
import subprocess
import logging
import os
import time
from pydub.utils import which

# ========== HARDCODED API KEY ==========
GROQ_API_KEY = "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"

# ========== INITIALIZE CLIENTS ==========
groq_client = Groq(api_key=GROQ_API_KEY)

# ========== CONSTANTS ==========
WAKE_WORD = "lucy"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
AUDIO_FILE = "response.wav"

# ========== LOGGING CONFIGURATION ==========
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ========== SUPPRESS ALSA ERRORS ==========
os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"
os.environ["SDL_AUDIODRIVER"] = "alsa"
os.environ["AUDIODEV"] = "hw:1,0"  # Modify based on your Raspberry Pi audio setup

# ========== SPEECH RECOGNIZER ==========
recognizer = sr.Recognizer()

# ========== IMAGE ENCODING FUNCTION ==========
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# ========== IMAGE CAPTURE FUNCTION ==========
def capture_image():
    image_path = "image.jpg"
    try:
        subprocess.run(["libcamera-still", "-o", image_path, "--nopreview"], check=True, stderr=subprocess.DEVNULL)
        if os.path.exists(image_path):
            logging.info(f"Image captured: {image_path}")
            return image_path
    except Exception as e:
        logging.error(f"Error capturing image: {e}")
    return None

# ========== TEXT-TO-SPEECH FUNCTION (Google TTS) ==========
def play_tts_response(text):
    try:
        tts = gtts.gTTS(text=text, lang="en", slow=False)
        tts.save(AUDIO_FILE)
        subprocess.run(["aplay", AUDIO_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Use aplay
    except Exception as e:
        logging.error(f"TTS error: {e}")

# ========== SPEECH-TO-TEXT FUNCTION ==========
def get_audio_input(wait_for_wake_word=True):
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            logging.info("Listening for input...")
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)
        text = recognizer.recognize_google(audio).lower()
        logging.info(f"User said: {text}")

        if wait_for_wake_word and WAKE_WORD in text:
            play_tts_response("Hello! How can I assist you?")
            return get_audio_input(False)
        return text
    except (sr.UnknownValueError, sr.WaitTimeoutError):
        return None
    except sr.RequestError as e:
        logging.error(f"STT request error: {e}")
        return None

# ========== MAIN CONVERSATION LOOP ==========
try:
    while True:
        user_input = get_audio_input()
        if not user_input:
            continue
        
        if user_input == "restart":
            play_tts_response("I have cleared the context.")
            continue
        
        if "image" in user_input or "picture" in user_input:
            image_path = capture_image()
            if image_path:
                base64_image = encode_image(image_path)
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }]
                model = GROQ_VISION_MODEL
            else:
                play_tts_response("I couldn't capture an image. Try again.")
                continue
        else:
            messages = [{"role": "user", "content": user_input}]
            model = GROQ_CHAT_MODEL

        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=0.7,
            max_tokens=200  # Ensure concise responses
        )

        response_text = chat_completion.choices[0].message.content.strip()
        play_tts_response(response_text)

except KeyboardInterrupt:
    logging.info("Exiting conversation loop.")  

