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
from gtts import gTTS
from playsound import playsound

# ========== HARDCODED API KEYS ==========  
GROQ_API_KEY = "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"
ELEVENLABS_API_KEY = "your_elevenlabs_api_key"

# ========== INITIALIZE CLIENTS ==========  
groq_client = Groq(api_key=GROQ_API_KEY)
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# ========== CONSTANTS ==========  
WAKE_WORD = "lucy"
VOICE_ID = "cgSgspJ2msm6clMCkdW9"
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
USE_GOOGLE_TTS = True  # Toggle between Google TTS and ElevenLabs

# ========== LOGGING CONFIGURATION ==========  
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ========== SPEECH RECOGNIZER ==========  
recognizer = sr.Recognizer()

# ========== GOOGLE TTS FUNCTION ==========  
def play_google_tts(text):
    tts = gTTS(text=text, lang='en')
    tts.save("response.mp3")
    playsound("response.mp3")
    os.remove("response.mp3")

# ========== ELEVENLABS TTS FUNCTION ==========  
def play_elevenlabs_tts(text):
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
def get_audio_input():
    logging.info("Listening for user input...")
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=10)
        text = recognizer.recognize_google(audio).lower()
        logging.info("User said: %s", text)
        return text
    except sr.UnknownValueError:
        logging.warning("Didn't catch that. Please try again.")
        return get_audio_input()
    except sr.RequestError as e:
        logging.error("Could not request results from Google Speech Recognition: %s", e)
        return None

# ========== MAIN CONVERSATION LOOP ==========  
try:
    while True:
        user_input = get_audio_input()
        if user_input:
            response_text = "Hello! How can I assist you today?"
            logging.info("Assistant said: %s", response_text)
            
            if USE_GOOGLE_TTS:
                play_google_tts(response_text)
            else:
                play_elevenlabs_tts(response_text)
except KeyboardInterrupt:
    logging.info("Exiting the conversation loop.")

