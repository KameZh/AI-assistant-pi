import json, os, queue, re, requests, time
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from faster_whisper import WhisperModel
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
import scipy.io.wavfile as wav

# --- CONFIGURATION ---
WAKE_WORD = "beep"
VOSK_PATH = "/home/samol/vosk-model-small-en-us-0.15"
PIPER_EN = "/home/samol/Desktop/ai-assist/en_US-lessac-medium.onnx" 
PIPER_BG = "/home/samol/Desktop/ai-assist/bg_BG-dimitar-medium.onnx"
PIPER_EXE = "/home/samol/Desktop/ai-assist/piper/piper"
PC_TAILSCALE_IP = "100.X.X.X" 
AI_MODEL = "gemma4:e2b"
USE_THINKING = False

# --- 1. STARTUP MENU (LANGUAGE LOCK) ---
print("\n" + "="*45)
print(" PIP ASSISTANT - STARTUP CONFIGURATION")
print("="*45)
while True:
    lang_choice = input("What language will you be using (b - bulgarian / e - english)? ").strip().lower()
    if lang_choice in ['b', 'e']:
        break
    print("Invalid choice. Please type 'b' or 'e'.")

if lang_choice == 'b':
    STT_LANG = "bg"
    ACTIVE_TTS = PIPER_BG
    SYS_LANG = "Bulgarian"
else:
    STT_LANG = "en"
    ACTIVE_TTS = PIPER_EN
    SYS_LANG = "English"

print(f"\n=> Language securely locked to: {SYS_LANG}")
print("=> Booting AI Engines...\n")

# --- 2. ENGINE INITIALIZATION ---
stt_model = WhisperModel("tiny", device="cpu", compute_type="int8")
audio_q = queue.Queue()

# Lock Gemma's persona into the chosen language
base_instructions = f"Your name is Pip. You are a helpful voice assistant. You MUST respond strictly and concisely in {SYS_LANG}.Don't suggest anything harmful. Use slurs only if user uses first. Refer to user as user. The user's name is user if not specified otherwise. Try to be as helpful as possible. Acknowledge this."
if USE_THINKING:
    base_instructions += " Think step-by-step and lay out your logic before providing your final answer."

chat_history = [
    {"role": "user", "content": base_instructions},
    {"role": "assistant", "content": f"Understood. My name is Pip and I am ready. I will only speak in {SYS_LANG}."}
]

def get_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return f"{float(f.read()) / 1000.0:.1f}"
    except: return "0.0"

def speak(text, live):
    if not text: return
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    clean_text = re.sub(r'<\|.*?\|>', '', clean_text).strip()
    
    # Clean text differently depending on the chosen language
    if STT_LANG == "bg":
        clean_tts = re.sub(r'[^a-zA-Z0-9\s.,?!а-яА-Я]', ' ', clean_text).strip()
    else:
        clean_tts = re.sub(r'[^a-zA-Z0-9\s.,?!]', ' ', clean_text).strip()
        
    live.update(Panel(Text(f"Pip: {clean_tts}\nStatus: Speaking...")))
    os.system(f"echo '{clean_tts}' | {PIPER_EXE} --model {ACTIVE_TTS} --output_raw | aplay -D plughw:2,0 -r 22050 -f S16_LE -t raw -q")

def ask_pc(question):
    global chat_history
    if len(chat_history) > 6: 
        chat_history = chat_history[:2] + chat_history[-4:]
    chat_history.append({"role": "user", "content": question})
    payload = {
        "model": AI_MODEL,
        "messages": chat_history,
        "stream": False
    }
    try:
        url = f"http://{PC_TAILSCALE_IP}:11434/api/chat"
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code == 200:
            ans = r.json().get("message", {}).get("content", "").strip()
            chat_history.append({"role": "assistant", "content": ans})
            return ans
        return f"PC Server Error: {r.status_code}"
    except Exception as e:
        return "Tunnel Error: Could not reach the PC."

def main():
    v_model = Model(VOSK_PATH)
    rec = KaldiRecognizer(v_model, 48000)
    
    def callback(indata, frames, time, status): 
        audio_q.put(bytes(indata))
    
    think_status = "ON" if USE_THINKING else "OFF"
    
    with sd.RawInputStream(samplerate=48000, blocksize=8000, dtype='int16', channels=1, callback=callback):
        with Live(Panel(Text(f"Booting Pip in {SYS_LANG}...")), refresh_per_second=4) as live:
            while True:
                temp = get_temp()
                data = audio_q.get()
                if rec.AcceptWaveform(data):
                    heard = json.loads(rec.Result()).get("text", "")
                    if WAKE_WORD in heard.lower():
                        live.update(Panel(Text(f"Status: Listening... | Temp: {temp}°C | Lang: {STT_LANG.upper()}", style="yellow")))
                        with audio_q.mutex: audio_q.queue.clear()
                        frames_list = []
                        start_time = time.time()
                        while time.time() - start_time < 5.0:
                            try:
                                frames_list.append(audio_q.get(timeout=0.1))
                            except queue.Empty:
                                pass
                        raw_bytes = b"".join(frames_list)
                        audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
                        wav.write("query.wav", 48000, audio_data)
                        
                        live.update(Panel(Text(f"Status: Transcribing... | Temp: {temp}°C", style="magenta")))
                        
                        # THE FIX: Force Whisper to strictly use the selected language
                        segments, _ = stt_model.transcribe("query.wav", beam_size=5, language=STT_LANG)
                        q_text = "".join([s.text for s in segments]).strip()
                        
                        if q_text and len(q_text) > 2:
                            live.update(Panel(Text(f"Q: {q_text}\nStatus: PC Thinking... | Temp: {temp}°C", style="cyan")))
                            ans = ask_pc(q_text)
                            speak(ans, live)
                            live.update(Panel(Text(f"Last Q: {q_text}\nPip: {ans}\n\nStatus: Waiting for 'Pi' | Temp: {temp}°C | Lang: {STT_LANG.upper()}", style="green")))
                        else:
                            live.update(Panel(Text(f"Failed to hear you. Whisper heard: '{q_text}'", style="red")))
                            time.sleep(3)
                            live.update(Panel(Text(f"Status: Waiting for 'Pip' | Temp: {temp}°C | Lang: {STT_LANG.upper()}", style="green")))
                        
                        with audio_q.mutex: audio_q.queue.clear()
                        live.update(Panel(Text(f"Status: Waiting for 'Pip' | Temp: {temp}°C | Lang: {STT_LANG.upper()}", style="green")))
                else:
                    live.update(Panel(Text(f"Status: Waiting for 'Pip' | Temp: {temp}°C | Lang: {STT_LANG.upper()}", style="green")))

if __name__ == "__main__":
    main()
