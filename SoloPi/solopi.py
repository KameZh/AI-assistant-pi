import json, os, queue, re, requests, time, datetime, subprocess
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from faster_whisper import WhisperModel
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
import scipy.io.wavfile as wav
import wikipedia

import board
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd

MIC_DEVICE_ID = 1  
MIC_SAMPLE_RATE = 48000

WAKE_WORD = "pip"
VOSK_PATH = "/home/<USER>/vosk-model-small-en-us-0.15"
PIPER_EN = "/home/<USER>/Desktop/ai-assist/en_US-lessac-medium.onnx" 
PIPER_BG = "/home/<USER>/Desktop/ai-assist/bg_BG-dimitar-medium.onnx"
PIPER_EXE = "/home/<USER>/Desktop/ai-assist/piper/piper"

PC_TAILSCALE_IP = "100.X.X.X" 
AI_MODEL = "gemma4:e2b"
USE_THINKING = False

try:
    lcd_rs = digitalio.DigitalInOut(board.D25)
    lcd_en = digitalio.DigitalInOut(board.D24)
    lcd_d4 = digitalio.DigitalInOut(board.D23)
    lcd_d5 = digitalio.DigitalInOut(board.D17)
    lcd_d6 = digitalio.DigitalInOut(board.D27)  
    lcd_d7 = digitalio.DigitalInOut(board.D22)

    def flush_parasitic_power():
        for pin in [lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7]:
            pin.direction = digitalio.Direction.OUTPUT
            pin.value = False  
        time.sleep(1) 

    flush_parasitic_power()

    lcd_columns = 16
    lcd_rows = 2
    lcd = characterlcd.Character_LCD_Mono(
        lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7, lcd_columns, lcd_rows
    )
    LCD_AVAILABLE = True
except Exception as e:
    print(f"[Warning] LCD failed to initialize. Check wiring. Error: {e}")
    LCD_AVAILABLE = False

LAST_LCD_LINE1 = ""
LAST_LCD_LINE2 = ""

def set_lcd(line1, line2=""):
    global LAST_LCD_LINE1, LAST_LCD_LINE2
    if LCD_AVAILABLE:
        str_line1 = str(line1)[:16]
        str_line2 = str(line2)[:16]
        
        if str_line1 != LAST_LCD_LINE1 or str_line2 != LAST_LCD_LINE2:
            lcd.clear()
            time.sleep(0.1) 
            lcd.message = f"{str_line1}\n{str_line2}"
            LAST_LCD_LINE1 = str_line1
            LAST_LCD_LINE2 = str_line2
# ==========================================

print("\n" + "="*45)
print(" PIP ASSISTANT - OMNI-NODE CONFIGURATION")
print("="*45)

set_lcd("Select language:", "Waiting for User")

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
print("=> Booting AI Engines... (This will take a moment)\n")

set_lcd("Loading AI...", "1/2: Whisper")
stt_model = WhisperModel("tiny", device="cpu", compute_type="int8")

set_lcd("Loading AI...", "2/2: Vosk")
v_model = Model(VOSK_PATH)
rec = KaldiRecognizer(v_model, MIC_SAMPLE_RATE)

audio_q = queue.Queue()

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

def speak(text, live, update_lcd=True):
    if not text: return
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    clean_text = re.sub(r'<\|.*?\|>', '', clean_text).strip()
    clean_text = re.sub(r'\[Context:.*?\]', '', clean_text).strip() 
    
    if STT_LANG == "bg":
        clean_tts = re.sub(r'[^a-zA-Z0-9\s.,?!а-яА-Я]', ' ', clean_text).strip()
    else:
        clean_tts = re.sub(r'[^a-zA-Z0-9\s.,?!]', ' ', clean_text).strip()
        
    live.update(Panel(Text(f"Pip: {clean_tts}\nStatus: Speaking...")))
    
    if update_lcd:
        set_lcd("Status:", "Speaking...")
    
    os.system(f"echo '{clean_tts}' | {PIPER_EXE} --model {ACTIVE_TTS} --output_file /tmp/pip_speech.wav")
    os.system("mpv --no-terminal --volume=150 /tmp/pip_speech.wav > /dev/null 2>&1")

def process_skills(question):
    q_lower = question.lower()
    system_injection = ""
    lcd_l1, lcd_l2 = None, None

    if any(w in q_lower for w in ["time", "часът", "date", "дата"]):
        now = datetime.datetime.now()
        lcd_l1 = "Current Time:"
        lcd_l2 = now.strftime("%H:%M")
        system_injection += f"[Context: The current time and date is {now.strftime('%I:%M %p on %A, %B %d, %Y')}.] "

    elif any(w in q_lower for w in ["weather", "времето", "temperature", "температура"]):
        try:
            wttr = requests.get("https://wttr.in/?format=%C+%t", timeout=5).text.strip()
            lcd_l1 = "Weather:"
            lcd_l2 = wttr[:16]
            system_injection += f"[Context: The current weather is {wttr}.] "
        except:
            lcd_l1 = "Weather:"
            lcd_l2 = "Network Error"
            system_injection += "[Context: Network error, weather unavailable.] "

    elif any(w in q_lower for w in ["system status", "системен статус", "how are you feeling", "статус"]):
        temp = get_temp()
        free = os.popen("free -m").readlines()[1].split()
        ram = f"{free[2]}M/{free[1]}M"
        lcd_l1 = f"CPU: {temp}C"
        lcd_l2 = f"RAM: {ram}"[:16]
        system_injection += f"[Context: Your Raspberry Pi CPU temperature is {temp}°C and RAM usage is {free[2]}MB used out of {free[1]}MB.] "

    elif any(w in q_lower for w in ["wikipedia", "уикипедия"]):
        triggers = ["search wikipedia for", "what is on wikipedia about", "wikipedia", "уикипедия", "търси в", "за"]
        search_term = q_lower
        for t in triggers:
            search_term = search_term.replace(t, "")
        search_term = search_term.strip()
        
        if len(search_term) > 2:
            try:
                wikipedia.set_lang("bg" if STT_LANG == "bg" else "en")
                summary = wikipedia.summary(search_term, sentences=2)
                lcd_l1 = "Wikipedia:"
                lcd_l2 = search_term[:16]
                system_injection += f"[Context from Wikipedia: {summary}. Answer based on this.] "
            except:
                system_injection += "[Context: Could not find Wikipedia article.] "

    if system_injection:
        return f"{system_injection}\nUser asked: {question}", lcd_l1, lcd_l2
    
    return question, lcd_l1, lcd_l2

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
    def callback(indata, frames, time, status): 
        audio_q.put(bytes(indata))
    
    with sd.RawInputStream(samplerate=MIC_SAMPLE_RATE, blocksize=8000, dtype='int16', channels=1, device=MIC_DEVICE_ID, callback=callback):
        with Live(Panel(Text(f"Booting Pip in {SYS_LANG}...")), refresh_per_second=4) as live:
            set_lcd("Omni-Node", "Online & Ready")
            time.sleep(1)
            
            last_active_time = time.time()
            last_ui_update_time = 0 
            
            while True:
                data = audio_q.get()
                wake_detected = False
                
                if rec.AcceptWaveform(data):
                    heard = json.loads(rec.Result()).get("text", "")
                    if WAKE_WORD in heard.lower():
                        wake_detected = True

                if wake_detected:
                    last_active_time = time.time()
                    temp = get_temp()
                    set_lcd("Status:", "Listening...")
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
                    wav.write("query.wav", MIC_SAMPLE_RATE, audio_data)
                    
                    set_lcd("Status:", "Transcribing...")
                    live.update(Panel(Text(f"Status: Transcribing... | Temp: {temp}°C", style="magenta")))
                    segments, _ = stt_model.transcribe("query.wav", beam_size=5, language=STT_LANG)
                    q_text = "".join([s.text for s in segments]).strip()
                    
                    if q_text and len(q_text) > 2:
                        set_lcd("Status:", "PC Thinking...")
                        live.update(Panel(Text(f"Q: {q_text}\nStatus: PC Thinking... | Temp: {temp}°C", style="cyan")))
                        
                        processed_text, lcd1, lcd2 = process_skills(q_text)
                        ans = ask_pc(processed_text)
                        
                        if lcd1:
                            set_lcd(lcd1, lcd2)
                            speak(ans, live, update_lcd=False)
                            time.sleep(2) 
                        else:
                            speak(ans, live, update_lcd=True)
                        
                        live.update(Panel(Text(f"Last Q: {q_text}\nPip: {ans}\n\nStatus: Waiting for '{WAKE_WORD}' | Temp: {temp}°C", style="green")))
                    else:
                        set_lcd("Error:", "Heard nothing")
                        live.update(Panel(Text(f"Failed to hear you. Whisper heard: '{q_text}'", style="red")))
                        time.sleep(3)
                        
                    with audio_q.mutex: audio_q.queue.clear()
                    
                    last_active_time = time.time() 
                    last_ui_update_time = 0
                
                else:
                    now = time.time()
                    if now - last_active_time > 10.0:
                        if now - last_ui_update_time >= 5.0:
                            clock_str = datetime.datetime.now().strftime("%H:%M")
                            temp = get_temp() 
                            set_lcd(f"Time: {clock_str}", f"Temp: {temp}C")
                            live.update(Panel(Text(f"Status: IDLE (Zzz) | Time: {clock_str} | Temp: {temp}°C", style="dim white")))
                            last_ui_update_time = now
                    else:
                        if now - last_ui_update_time >= 5.0:
                            temp = get_temp()
                            set_lcd(f"Wait: {WAKE_WORD}", f"Temp: {temp}C")
                            live.update(Panel(Text(f"Status: Waiting for '{WAKE_WORD}' | Temp: {temp}°C", style="green")))
                            last_ui_update_time = now

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down Omni-Node...")
        if LCD_AVAILABLE:
            lcd.clear()
            time.sleep(0.1)
            flush_parasitic_power()
