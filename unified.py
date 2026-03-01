import json, os, sys, queue, subprocess, re, requests, threading, time
import sounddevice as sd
import numpy as np
from vosk import Model, KaldiRecognizer
from rich.console import Console
from rich.panel import Panel
import termios, tty, select, signal

# --- CONFIG ---
PC_HOST = "http://100.69.226.17:11434" # Your PC IP
MODEL = "gpt-oss:20b"
VOSK_MODEL_PATH = "/home/samol/vosk-model/vosk-model-small-en-us-0.15"
PIPER_MODEL = "/home/samol/Desktop/en_US-lessac-medium.onnx"
WAKE_WORD = "right"

console = Console()
audio_q = queue.Queue()
is_processing = False
speech_process = None
chat_history = [
    {"role": "system", "content": "You are Pip. Use web_search for current news. If a search fails, try different keywords. Be detailed but concise. Skip names in politics unless asked."}
]

# --- SPACE BAR INTERRUPT LOGIC ---
def is_space_pressed():
    """Check stdin for a spacebar press without blocking."""
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        key = sys.stdin.read(1)
        return key == ' '
    return False

# --- WEB SEARCH (Self-Correcting) ---
def web_search(query: str):
    # Keep queries focused for DuckDuckGo
    query = " ".join(query.split()[:6])
    console.print(f"[bold yellow]🔍 Web Search:[/][italic] {query}[/]")
    try:
        r = requests.get(f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1", timeout=10)
        data = r.json()
        
        # Priority 1: Abstract
        result = data.get("AbstractText", "")
        
        # Priority 2: Related Topics (if Abstract is empty)
        if not result and data.get("RelatedTopics"):
            topics = [t.get("Text") for t in data["RelatedTopics"] if "Text" in t]
            if topics:
                result = "Found these related facts: " + " | ".join(topics[:3])
        
        if not result:
            return "ERROR_NO_RESULTS: The search found nothing. Try different keywords."
            
        return result
    except Exception as e:
        return f"Search error: {str(e)}"

# --- TTS ENGINE (With Process Group Kill) ---
def speak(text):
    global speech_process
    if not text or "ERROR_NO_RESULTS" in text: return
    
    # Clean text for Shell/Piper
    clean = re.sub(r'[|#*_\-–—]', ' ', text).replace("'", "'\\''")
    console.print(Panel(clean, title="[bold magenta]Pip Speaks", border_style="magenta"))
    
    # Using os.setsid to create a process group so we can kill piper+aplay together
    cmd = f"echo '{clean}' | piper --model {PIPER_MODEL} --output_raw 2>/dev/null | aplay -r 22050 -f S16_LE -t raw"
    speech_process = subprocess.Popen(cmd, shell=True, preexec_fn=os.setsid)
    
    while speech_process.poll() is None:
        if is_space_pressed():
            os.killpg(os.getpgid(speech_process.pid), signal.SIGTERM)
            console.print("[bold red]🛑 Stopped by user.[/]")
            break
        time.sleep(0.05)

# --- BRAIN (Multi-Turn Search Loop) ---
def ask_pc(question):
    global chat_history
    chat_history.append({"role": "user", "content": question})

    tools = [{
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search for real-time info or news.',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']},
        }
    }]

    # Loop allows the AI to refine its search if the first one fails
    for _ in range(3):
        try:
            payload = {"model": MODEL, "messages": chat_history, "tools": tools, "stream": False}
            r = requests.post(f"{PC_HOST}/api/chat", json=payload, timeout=90).json()
            msg = r.get("message", {})

            if msg.get("tool_calls"):
                for tool in msg["tool_calls"]:
                    if tool["function"]["name"] == "web_search":
                        search_data = web_search(tool["function"]["arguments"]["query"])
                        chat_history.append(msg)
                        chat_history.append({"role": "tool", "content": search_data})
                continue # Loop back to let AI process the new data
            
            ans = msg.get("content", "").strip()
            if ans:
                chat_history.append({"role": "assistant", "content": ans})
                return ans
        except Exception as e:
            return f"Brain Connection Error: {e}"

    return "I couldn't find enough information after several searches."

# --- MAIN LOOP (Active Listening Logic) ---
def main():
    global is_processing
    console.print("[yellow]Initialising Models...[/]")
    vosk_model = Model(VOSK_MODEL_PATH)
    rec = KaldiRecognizer(vosk_model, 16000)

    is_waiting_for_query = False

    def callback(indata, frames, time, status):
        audio_q.put(bytes(indata))

    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
        console.clear()
        console.print(Panel.fit("PIP ONLINE", style="bold green", subtitle="Wake: 'Right' | Space: Stop"))
        
        while True:
            data = audio_q.get()
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                heard = res.get("text", "").lower()
                if not heard: continue

                if not is_waiting_for_query:
                    if WAKE_WORD in heard:
                        console.print("[bold yellow]!!! WAKE WORD DETECTED !!![/]")
                        is_waiting_for_query = True
                        
                        # Check if question was asked in the same breath
                        parts = heard.split(WAKE_WORD)
                        if len(parts) > 1 and parts[1].strip():
                            question = parts[1].strip()
                            console.print(f"[cyan]Heard:[/] {question}")
                            ans = ask_pc(question)
                            speak(ans)
                            is_waiting_for_query = False
                        else:
                            console.print("[cyan]Yes? Listening...[/]")
                else:
                    # Capture the full question after the wake word
                    is_processing = True
                    console.print(f"[cyan]Question:[/] {heard}")
                    ans = ask_pc(heard)
                    speak(ans)
                    
                    # Clean up
                    with audio_q.mutex: audio_q.queue.clear()
                    is_processing = False
                    is_waiting_for_query = False
                    console.print("[dim]Waiting for 'Right'...[/]")

if __name__ == "__main__":
    # Configure terminal for non-blocking single-key reads
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        main()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)