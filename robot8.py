from groq import Groq
import speech_recognition as sr
import gtts
import pyaudio
import io
import base64
import subprocess
import logging
import os
import time
from pydub import AudioSegment
from pydub.playback import play
from pydub.utils import which

# ========== HARDCODED API KEY ==========
GROQ_API_KEY = "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"

# ========== INITIALIZE CLIENTS ==========
groq_client = Groq(api_key=GROQ_API_KEY)

# ========== CONSTANTS ==========
WAKE_WORD = "lucy"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
AUDIO_FILE = "response.mp3"

# ========== LOGGING CONFIGURATION ==========
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ========== SPEECH RECOGNIZER ==========
recognizer = sr.Recognizer()

# ========== SETUP FFmpeg ==========
AudioSegment.converter = which("ffmpeg")

# ========== IMAGE ENCODING FUNCTION ==========
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# ========== IMAGE CAPTURE FUNCTION ==========
def capture_image():
    image_path = "image.jpg"
    try:
        subprocess.run(["libcamera-still", "-o", image_path, "--nopreview"], check=True)
        if os.path.exists(image_path):
            logging.info(f"Image captured and saved as {image_path}")
            return image_path
        else:
            logging.error(f"Image file '{image_path}' was not saved.")
            return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to capture image: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error occurred: {e}")
        return None

# ========== TEXT-TO-SPEECH FUNCTION (Google TTS with Female Voice) ==========
def play_tts_response(text):
    try:
        tts = gtts.gTTS(text=text, lang="en", slow=False)
        tts.save(AUDIO_FILE)

        # Play the audio using FFmpeg (better performance on Raspberry Pi)
        subprocess.run(["ffplay", "-nodisp", "-autoexit", AUDIO_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logging.info(f"Spoken response: {text}")

    except Exception as e:
        logging.error(f"Error in text-to-speech: {e}")

# ========== SPEECH-TO-TEXT FUNCTION ==========
def get_audio_input(wait_for_wake_word=True):
    if wait_for_wake_word:
        logging.info(f"Listening for wake word '{WAKE_WORD}'...")
    else:
        logging.info("Listening for user input...")

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)

        text = recognizer.recognize_google(audio).lower()

        if wait_for_wake_word:
            if WAKE_WORD in text:
                logging.info("Wake word detected. Starting conversation...")
                play_tts_response("Hello! How can I assist you?")
                return get_audio_input(wait_for_wake_word=False)
            elif "restart" in text or "reset" in text:
                return "restart"
        else:
            logging.info("User said: %s", text)
            if "look at" in text or "what do you see" in text or "picture" in text or "image" in text:
                return "vision_request" + text
            return text
    except sr.WaitTimeoutError:
        logging.warning("Listening timed out. Reverting to wake word mode.")
        return None
    except sr.UnknownValueError:
        logging.warning("Didn't catch that. Please try again.")
        return get_audio_input(wait_for_wake_word)
    except sr.RequestError as e:
        logging.error(f"Could not request results from Google Speech Recognition service: {e}")
        return None

# ========== MAIN CONVERSATION LOOP ==========
try:
    wait_for_wake_word = True
    while True:
        user_input = get_audio_input(wait_for_wake_word)
        if user_input:
            if user_input.lower() == "restart":
                logging.info("Restarting the conversation...")
                context_window = []
                response_text = "I just cleared the context window."
                wait_for_wake_word = True

            elif "vision_request" in user_input:
                image_path = capture_image()
                if image_path:
                    base64_image = encode_image(image_path)

                    chat_completion = groq_client.chat.completions.create(
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"What do you see in this image? {user_input[14:]}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                            ]
                        }],
                        model=GROQ_VISION_MODEL,
                    )

                    response_text = chat_completion.choices[0].message.content
                else:
                    response_text = "I'm sorry, but I couldn't capture an image. Could you please try again?"

            else:
                chat_completion = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": user_input}],
                    model=GROQ_CHAT_MODEL,
                    temperature=1.0,
                    max_tokens=1024,
                )

                response_text = chat_completion.choices[0].message.content
                logging.info("Assistant said: %s", response_text)

            play_tts_response(response_text)
            wait_for_wake_word = False
        else:
            wait_for_wake_word = True

except KeyboardInterrupt:
    logging.info("Exiting the conversation loop.") 

