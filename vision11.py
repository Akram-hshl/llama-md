from groq import Groq
import speech_recognition as sr
import pyaudio
import io
import base64
import subprocess
import logging
import os
from pydub import AudioSegment
from pydub.utils import which
from TTS.api import TTS  # Coqui TTS

# ========== HARDCODED API KEYS ==========  
GROQ_API_KEY = "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"

# ========== INITIALIZE CLIENTS ==========  
groq_client = Groq(api_key=GROQ_API_KEY)

# ========== CONSTANTS ==========  
WAKE_WORD = "lucy"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"

# ========== LOGGING CONFIGURATION ==========  
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ========== SPEECH RECOGNIZER ==========  
recognizer = sr.Recognizer()

# ========== INITIAL CONTEXT ==========  
initial_context = [
    {
        "role": "system",
        "content": f"You are a helpful voice assistant named {WAKE_WORD}. Your responses should be optimal for speech output (concise, conversational, and pronunciation-friendly).",
    }
]
context_window = initial_context.copy()

# ========== SETUP FFmpeg and FFprobe ==========  
AudioSegment.ffmpeg = which("ffmpeg")
AudioSegment.ffprobe = which("ffprobe")

# ========== INITIALIZE Coqui TTS ==========  
tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")

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

# ========== TEXT-TO-SPEECH FUNCTION (Coqui TTS) ==========  
def play_tts_response(text):
    tts.tts_to_file(text=text, file_path="response.wav")
    play_audio_file("response.wav")

# ========== AUDIO PLAYBACK FUNCTION ==========  
def play_audio_file(file_path):
    if os.path.exists(file_path):
        subprocess.run(["aplay", file_path])
    else:
        logging.error(f"Audio file '{file_path}' not found!")

# ========== SPEECH-TO-TEXT FUNCTION ==========  
def get_audio_input(wait_for_wake_word=True):
    if wait_for_wake_word:
        logging.info("Listening for wake word '%s'...", WAKE_WORD)
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
                play_tts_response("Hell yeah! What's poppin?")
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
        logging.error("Could not request results from Google Speech Recognition service: %s", e)
        return None

# ========== MAIN CONVERSATION LOOP ==========  
try:
    wait_for_wake_word = True
    while True:
        user_input = get_audio_input(wait_for_wake_word)
        if user_input:
            if user_input.lower() == "restart":
                logging.info("Restarting the conversation...")
                context_window = [context_window[0]]
                response_text = "I just cleared the context window"
                wait_for_wake_word = True

            elif "vision_request" in user_input:
                image_path = capture_image()
                if image_path:
                    base64_image = encode_image(image_path)
                    
                    chat_completion = groq_client.chat.completions.create(
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"What do you see in this image? If it's text, code, or math, read it aloud clearly. {user_input[14:]}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                            ]
                        }],
                        model=GROQ_VISION_MODEL,
                    )

                    response_text = chat_completion.choices[0].message.content
                    context_window.append({"role": "user", "content": user_input})
                    context_window.append({"role": "assistant", "content": response_text})
                else:
                    response_text = "I'm sorry, but I couldn't capture an image. Could you please try again?"

            else:
                context_window.append({"role": "user", "content": user_input})

                chat_completion = groq_client.chat.completions.create(
                    messages=context_window,
                    model=GROQ_CHAT_MODEL,
                    temperature=0.6,
                    max_tokens=1024,
                )

                response_text = chat_completion.choices[0].message.content
                context_window.append({"role": "assistant", "content": response_text})
                logging.info("Assistant said: %s", response_text)

            play_tts_response(response_text)
            wait_for_wake_word = False
        else:
            wait_for_wake_word = True

except KeyboardInterrupt:
    logging.info("Exiting the conversation loop.")

