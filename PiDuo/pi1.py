import json, os, sys, queue, subprocess, re, requests
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from rich.console import Console
from rich.panel import Panel
from rich.status import Status

# --- UI SETUP ---
console = Console()

# --- CONFIG ---
PI2_URL = "http://192.168.5.2:5000/ask"
CLEAR_URL = "http://192.168.5.2:5000/clear" # New route for memory reset
VOSK_MODEL_PATH = "/home/samol/vosk-model/vosk-model-small-en-us-0.15"
PIPER_MODEL = "/home/samol/Desktop/en_US-lessac-medium.onnx"
WAKE_WORD = "right"
is_processing = False 

# --- INITIALIZATION ---
if not os.path.exists(PIPER_MODEL):
    console.print(f"[bold red]ERROR:[/] Voice file not found at {PIPER_MODEL}")
    sys.exit(1)

vosk_model = Model(VOSK_MODEL_PATH)
rec = KaldiRecognizer(vosk_model, 16000)
audio_q = queue.Queue()

def callback(indata, frames, time, status):
    if is_processing: return
    audio_np = np.frombuffer(indata, dtype='int16').astype(np.float32)
    audio_boosted = np.clip(audio_np * 3.0, -32768, 32767)
    audio_q.put(audio_boosted.astype('int16').tobytes())

def speak(text):
    if not text: return
    # Clean up formatting for TTS
    clean = re.sub(r'[|#*_\-–—]', ' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    # UI: Show what is being said
    console.print(Panel(clean, title="[bold magenta]Gemma Speaks", border_style="magenta"))
    
    # The "One-Patch" fluid streaming command
    cmd = f"echo '{clean}' | piper --model {PIPER_MODEL} --output_raw 2>/dev/null | aplay -r 22050 -f S16_LE -t raw"
    subprocess.run(cmd, shell=True)

def main():
    global is_processing
    is_listening = False
    
    console.clear()
    console.print(Panel.fit("GEMMA SYSTEM ONLINE", style="bold green", subtitle="Conversation Mode Active"))

    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
        with console.status("[bold cyan]Waiting for 'GEMMA'...") as status:
            while True:
                data = audio_q.get()
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    heard = res.get("text", "").lower()
                    if not heard: continue
                    
                    console.print(f"[dim]Heard: {heard}[/]")

                    if not is_listening:
                        if WAKE_WORD in heard:
                            console.print("[bold yellow]!!! WAKE WORD DETECTED !!![/]")
                            status.update("[bold yellow]I'm listening to you...")
                            is_listening = True
                    else:
                        # NEW: Check for Memory Clear command
                        if "clear memory" in heard or "forget everything" in heard:
                            console.print("[bold red]Action: Clearing Chat History[/]")
                            try:
                                requests.post(CLEAR_URL)
                                speak("Okay, I've cleared my memory. What should we talk about now?")
                            except:
                                console.print("[red]Could not reach PC to clear memory.[/]")
                            is_listening = False
                            continue

                        # Standard Question Processing
                        is_processing = True 
                        console.print(Panel(heard, title="[bold cyan]Question", border_style="cyan"))
                        
                        status.update("[bold magenta]Gemma is thinking...")
                        try:
                            # Send question to PC
                            r = requests.post(PI2_URL, json={"question": heard}, timeout=120)
                            ans = r.json().get("response", "I'm having trouble connecting to my brain.")
                            speak(ans)
                        except Exception as e:
                            console.print(f"[bold red]Network Error:[/] {e}")
                        
                        # Reset States for next turn
                        with audio_q.mutex: audio_q.queue.clear()
                        is_processing = False
                        is_listening = False
                        status.update("[bold cyan]Waiting for 'GEMMA'...")

if __name__ == "__main__":
    main()
