from groq import Groq
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
import speech_recognition as sr
import pyaudio
import io
import base64
import subprocess
import logging
import random
import time
from pydub import AudioSegment
from pydub.utils import which
import os

# ========== HARDCODED API KEYS ==========  
GROQ_API_KEY = "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"
ELEVENLABS_API_KEY = "sk_1f857187ddc681ed49276344a20188668b3546a776c9db28"

# ========== INITIALIZE CLIENTS ==========  
groq_client = Groq(api_key=GROQ_API_KEY)
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# ========== CONSTANTS ==========  
WAKE_WORD = "lucy"
VOICE_ID = "cgSgspJ2msm6clMCkdW9"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"  # Updated model
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

# ========== IMAGE ENCODING FUNCTION ==========  
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

# ========== IMAGE CAPTURE FUNCTION (FIXED) ==========  
def capture_image():
    image_path = "image.jpg"
    try:
        # Capture image using libcamera
        subprocess.run(["libcamera-still", "-o", image_path, "--nopreview"], check=True)

        # Check if the image file was created successfully
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

# ========== TEXT-TO-SPEECH FUNCTION ==========  
def play_tts_response(text):
    audio_stream = elevenlabs_client.text_to_speech.convert_as_stream(
        voice_id=VOICE_ID,
        optimize_streaming_latency="2",
        output_format="mp3_22050_32",
        text=text,
        model_id="eleven_turbo_v2_5",
        voice_settings=VoiceSettings(
            stability=0.3,
            similarity_boost=0.2,
            style=0.1,
        ),
    )
    play_audio_stream(audio_stream)

# ========== AUDIO PLAYBACK FUNCTION ==========  
def play_audio_stream(audio_stream):
    p = pyaudio.PyAudio()
    device_index = 0  # Update this if needed for other output devices
    audio_data = b"".join(chunk for chunk in audio_stream)
    audio = AudioSegment.from_mp3(io.BytesIO(audio_data))
    raw_data = audio.raw_data
    stream = p.open(format=p.get_format_from_width(audio.sample_width),
                    channels=audio.channels, rate=audio.frame_rate,
                    output=True, output_device_index=device_index)
    chunk_size = 1024
    offset = 0
    while offset < len(raw_data):
        chunk = raw_data[offset : offset + chunk_size]
        stream.write(chunk)
        offset += chunk_size
    stream.stop_stream()
    stream.close()
    p.terminate()

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
                        model=GROQ_VISION_MODEL,  # Using the updated vision model
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

