import json, os, sys, queue, subprocess, re, requests, threading, time
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from rich.console import Console
from rich.panel import Panel
import termios, tty, select, signal
from duckduckgo_search import DDGS # New, better search

# --- CONFIG ---
PC_HOST = "http://100.69.226.17:11434"
MODEL = "gpt-oss:20b"
VOSK_MODEL_PATH = "/home/samol/vosk-model/vosk-model-small-en-us-0.15"
PIPER_MODEL = "/home/samol/Desktop/en_US-lessac-medium.onnx"
WAKE_WORD = "right"

console = Console()
audio_q = queue.Queue()
is_processing = False
speech_process = None

# --- SPACE BAR INTERRUPT ---
def is_space_pressed():
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        key = sys.stdin.read(1)
        return key == ' '
    return False

# --- NEW ROBUST WEB SEARCH ---
def web_search(query: str):
    query = " ".join(query.split()[:8])
    console.print(f"[bold yellow]🔍 Deep Search:[/] {query}")
    try:
        with DDGS() as ddgs:
            # This grabs actual snippets from search results
            results = list(ddgs.text(query, max_results=2))
            if not results:
                return "No search results found."
            
            # Combine the snippets into one speakable string
            combined = " ".join([r['body'] for r in results])
            # Limit length so Pip doesn't talk for 10 minutes
            return combined[:600] 
    except Exception as e:
        return f"Search error: {str(e)}"

# --- TTS ENGINE ---
def speak(text):
    global speech_process
    if not text or "No search results" in text: 
        text = "I'm sorry, I couldn't find any info on that."
    
    clean = re.sub(r'[|#*_\-–—]', ' ', text).replace("'", " ").replace('"', ' ')
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    console.print(Panel(clean, title="[bold magenta]Pip Output", border_style="magenta"))
    
    cmd = f"echo '{clean}' | piper --model {PIPER_MODEL} --output_raw 2>/dev/null | aplay -r 22050 -f S16_LE -t raw -B 200000"
    speech_process = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
    
    try:
        while speech_process.poll() is None:
            if is_space_pressed():
                os.killpg(os.getpgid(speech_process.pid), signal.SIGTERM)
                console.print("[bold red]🛑 Stopped.[/]")
                break
            time.sleep(0.1)
    except Exception:
        pass

# --- BRAIN ---
def ask_pc(question):
    tools = [{
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Get live web info.',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']},
        }
    }]

    try:
        payload = {"model": MODEL, "messages": [{"role": "user", "content": question}], "tools": tools, "stream": False}
        r = requests.post(f"{PC_HOST}/api/chat", json=payload, timeout=90).json()
        msg = r.get("message", {})

        if msg.get("tool_calls"):
            results = []
            for tool in msg["tool_calls"]:
                if tool["function"]["name"] == "web_search":
                    data = web_search(tool["function"]["arguments"]["query"])
                    results.append(data)
            return " ".join(results)
        
        return msg.get("content", "I don't have an answer for that.")
    except Exception as e:
        return f"Error: {e}"

# --- MAIN ---
def main():
    global is_processing
    vosk_model = Model(VOSK_MODEL_PATH)
    rec = KaldiRecognizer(vosk_model, 16000)
    is_waiting = False

    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=lambda i,f,t,s: audio_q.put(bytes(i))):
        console.clear()
        console.print(Panel.fit("PIP READY (DEEP SEARCH MODE)", style="bold green"))
        
        while True:
            data = audio_q.get()
            if rec.AcceptWaveform(data):
                heard = json.loads(rec.Result()).get("text", "").lower()
                if not heard: continue

                if not is_waiting:
                    if WAKE_WORD in heard:
                        is_waiting = True
                        q = heard.split(WAKE_WORD)[-1].strip()
                        if q:
                            speak(ask_pc(q))
                            is_waiting = False
                else:
                    speak(ask_pc(heard))
                    is_waiting = False
                    with audio_q.mutex: audio_q.queue.clear()

if __name__ == "__main__":
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        main()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)