from datetime import date
from io import BytesIO
import threading
import queue
import time
import os

# Suppress unnecessary logs from libraries
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

import google.generativeai as genai
from gtts import gTTS
from gpiozero import LED
from pygame import mixer
import speech_recognition as sr

# Raspberry Pi LED Indicators
gled = LED(24)  # Green LED
rled = LED(25)  # Red LED

mixer.pre_init(frequency=24000, buffer=2048)
mixer.init()

# Add your Google Gemini API key
GENAI_API_KEY = "AIzaSyAy9Ec_6v2zBjNnwO5F6ftWWxodgfrlgkQ"

if len(GENAI_API_KEY) < 5:
    print(f"Please add your Google Gemini API key in the program. \n")
    quit()

# Configure Google Gemini API
genai.configure(api_key=GENAI_API_KEY)

# Initialize Google Gemini model
model = genai.GenerativeModel('gemini-1.5-flash',
    generation_config=genai.GenerationConfig(
        candidate_count=1,
        top_p=0.95,
        top_k=64,
        max_output_tokens=60,
        temperature=0.9,
    ))

# Start the chat model
chat = model.start_chat(history=[])

today = str(date.today())

# Initialize counters
numtext = numtts = numaudio = 0

# Speech Recognition Setup
rec = sr.Recognizer()
mic = sr.Microphone()

rec.dynamic_energy_threshold = False
rec.energy_threshold = 400  # Adjust based on noise level

# Convert text to speech and play
def speak_text(text):
    global rled
    mp3file = BytesIO()
    tts = gTTS(text, lang="en", tld='us')
    tts.write_to_fp(mp3file)

    mp3file.seek(0)
    rled.on()
    print("AI:", text)

    try:
        mixer.music.load(mp3file, "mp3")
        mixer.music.play()
        while mixer.music.get_busy():
            time.sleep(0.2)
    except KeyboardInterrupt:
        mixer.music.stop()
    finally:
        rled.off()
        mp3file = None

# Generate AI response using Google Gemini
def chatfun(request, text_queue, llm_done, stop_event):
    global numtext, chat
    response = chat.send_message(request, stream=True)
    
    shortstring = ''
    for chunk in response:
        try:
            if chunk.candidates[0].content.parts:
                ctext = chunk.candidates[0].content.parts[0].text.replace("*", "")
                shortstring += ctext
                text_queue.put(shortstring)
                print(shortstring, end='')
                shortstring = ''
        except Exception:
            continue

    text_queue.put(shortstring)
    numtext += 1
    append2log(f"AI: {response.candidates[0].content.parts[0].text} \n")
    llm_done.set()

# Process text to speech
def text2speech(text_queue, tts_done, llm_done, audio_queue, stop_event):
    global numtts
    time.sleep(1)
    
    while not stop_event.is_set():
        if not text_queue.empty():
            text = text_queue.get(timeout=1)
            try:
                mp3file1 = BytesIO()
                tts = gTTS(text, lang="en", tld='us')
                tts.write_to_fp(mp3file1)
            except Exception:
                continue
            
            audio_queue.put(mp3file1)
            numtts += 1
            text_queue.task_done()

        if llm_done.is_set() and numtts == numtext:
            tts_done.set()
            break

# Play audio response
def play_audio(audio_queue, tts_done, stop_event):
    global numtts, numaudio, rled

    while not stop_event.is_set():
        mp3audio1 = audio_queue.get()
        mp3audio1.seek(0)
        rled.on()

        mixer.music.load(mp3audio1, "mp3")
        mixer.music.play()
        while mixer.music.get_busy():
            time.sleep(0.2)

        numaudio += 1
        audio_queue.task_done()
        rled.off()

        if tts_done.is_set() and numtts == numaudio:
            break

# Save conversation log
def append2log(text):
    global today
    fname = 'chatlog-' + today + '.txt'
    with open(fname, "a", encoding='utf-8') as f:
        f.write(text + "\n")

# Main function
def main():
    global today, numtext, numtts, numaudio, chat

    print("Voice Assistant Started. Say 'Assistant' to activate.")

    sleeping = True  # Assistant starts in sleep mode
    while True:
        with mic as source:
            rec.adjust_for_ambient_noise(source, duration=1)
            print("Listening...")
            gled.on()

            try:
                audio = rec.listen(source, timeout=10)
                text = rec.recognize_google(audio, language="en").lower()
                print(f"You: {text}\n")

            except sr.UnknownValueError:
                print("Could not understand audio.")
                continue

            except sr.RequestError as e:
                print(f"Speech Recognition API error: {e}")
                continue

            gled.off()

            # Wake word detection
            if sleeping and "assistant" in text:
                request = text.split("assistant", 1)[-1].strip()
                sleeping = False
                chat = model.start_chat(history=[])
                speak_text("Hi, how can I help?")
                continue

            elif sleeping:
                continue

            # Stop command
            if "stop" in text or "exit" in text:
                speak_text("Goodbye!")
                sleeping = True
                continue

            append2log(f"You: {text}\n")

            # Initialize counters
            numtext = numtts = numaudio = 0

            # Create queues and events
            text_queue = queue.Queue()
            audio_queue = queue.Queue()
            llm_done = threading.Event()
            tts_done = threading.Event()
            stop_event = threading.Event()

            # Start processing threads
            llm_thread = threading.Thread(target=chatfun, args=(text, text_queue, llm_done, stop_event))
            tts_thread = threading.Thread(target=text2speech, args=(text_queue, tts_done, llm_done, audio_queue, stop_event))
            play_thread = threading.Thread(target=play_audio, args=(audio_queue, tts_done, stop_event))

            llm_thread.start()
            tts_thread.start()
            play_thread.start()

            # Wait for processing to finish
            llm_done.wait()
            llm_thread.join()
            tts_done.wait()
            audio_queue.join()
            stop_event.set()
            tts_thread.join()
            play_thread.join()

if __name__ == "__main__":
    main()
