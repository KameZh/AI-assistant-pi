import json, os, queue, re, requests, threading, time
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from faster_whisper import WhisperModel
from llama_cpp import Llama
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
import scipy.io.wavfile as wav

# --- CONFIGURATION ---
WAKE_WORD = "beep"
VOSK_PATH = "/home/samol/vosk-model-small-en-us-0.15"
PIPER_EN = "/home/samol/Desktop/ai-assist/en_US-lessac-medium.onnx" 
PIPER_BG = "/home/samol/Desktop/ai-assist/bg_BG-dimitar-medium.onnx"
MODEL_PATH = "/home/samol/Desktop/ai-assist/gemma4-e2b.gguf"

# 1. Initialize Whisper
stt_model = WhisperModel("tiny", device="cpu", compute_type="int8")

# 2. Initialize the Raw AI Engine
print("Loading Gemma 4 directly into memory... (This takes a moment)")
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=2048,      
    n_threads=2,     
    verbose=False    
)

audio_q = queue.Queue()
# Gemma requires a strict user/assistant format, so we fake the first interaction to set the persona.
chat_history = [
    {"role": "user", "content": "Your name is Pip. You are a helpful voice assistant. Respond concisely in the user's language (Bulgarian or English). Never give long explanations. Don't suggest anything harmful. Don't use emojis. Acknowledge this."},
    {"role": "assistant", "content": "Understood. My name is Pip and I am ready."}
]
def get_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return f"{float(f.read()) / 1000.0:.1f}"
    except: return "0.0"

def is_cyrillic(text):
    return bool(re.search('[а-яА-Я]', text))

def speak(text, live):
    if not text: return
    clean_text = re.sub(r'<\|.*?\|>', '', text).strip()
    model = PIPER_BG if is_cyrillic(clean_text) else PIPER_EN
    clean_tts = re.sub(r'[^a-zA-Z0-9\s.,?!а-яА-Я]', ' ', clean_text).strip()
    
    live.update(Panel(Text(f"Pip: {clean_tts}\nStatus: Speaking...")))
    os.system(f"echo '{clean_tts}' | piper --model {model} --output_raw | aplay -r 22050 -f S16_LE -t raw -q")

def ask_direct(question):
    global chat_history
    if len(chat_history) > 6: 
        chat_history = chat_history[:2] + chat_history[-4:]
    
    chat_history.append({"role": "user", "content": question})
    
    try:
        response = llm.create_chat_completion(
            messages=chat_history,
            max_tokens=40,
            temperature=0.4
        )
        ans = response["choices"][0]["message"]["content"].strip()
        chat_history.append({"role": "assistant", "content": ans})
        return ans
    except Exception as e:
        return f"Engine Error: {str(e)}"

def main():
    if not os.path.exists(VOSK_PATH):
        print("Error: Vosk model not found.")
        return

    v_model = Model(VOSK_PATH)
    rec = KaldiRecognizer(v_model, 48000)
    
    def callback(indata, frames, time, status): 
        audio_q.put(bytes(indata))
    
    with sd.RawInputStream(samplerate=48000, blocksize=8000, dtype='int16', channels=1, callback=callback):
        with Live(Panel(Text("Booting Pip...")), refresh_per_second=4) as live:
            while True:
                temp = get_temp()
                data = audio_q.get()
                if rec.AcceptWaveform(data):
                    heard = json.loads(rec.Result()).get("text", "")
                    if WAKE_WORD in heard.lower():
                        live.update(Panel(Text(f"Status: Listening... | Temp: {temp}°C", style="yellow")))
                        
                        # THE FIX: Harvest 5 seconds of audio from the already-running queue
                        with audio_q.mutex: audio_q.queue.clear()
                        frames_list = []
                        start_time = time.time()
                        
                        while time.time() - start_time < 5.0:  # Listen for 5 seconds
                            try:
                                frames_list.append(audio_q.get(timeout=0.1))
                            except queue.Empty:
                                pass
                        
                        # Convert the raw harvested bytes into a .wav file
                        raw_bytes = b"".join(frames_list)
                        audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
                        wav.write("query.wav", 48000, audio_data)
                        
                        live.update(Panel(Text(f"Status: Transcribing... | Temp: {temp}°C", style="magenta")))
                        segments, _ = stt_model.transcribe("query.wav", beam_size=5)
                        q_text = "".join([s.text for s in segments]).strip()
                        
                        if q_text and len(q_text) > 4:
                            live.update(Panel(Text(f"Q: {q_text}\nStatus: Thinking... | Temp: {temp}°C", style="cyan")))
                            ans = ask_direct(q_text)
                            speak(ans, live)
                        
                        with audio_q.mutex: audio_q.queue.clear()
                        live.update(Panel(Text(f"Status: Waiting for 'Pip' | Temp: {temp}°C", style="green")))
                else:
                    live.update(Panel(Text(f"Status: Waiting for 'Pip' | Temp: {temp}°C", style="green")))

if __name__ == "__main__":
    main()
