import json, os, sys, queue, subprocess, re, requests, threading, time, logging, signal
from dotenv import load_dotenv, dotenv_values 
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import termios, tty, select
from ddgs import DDGS

# --- 1. SETTINGS & CONFIG ---
load_dotenv()
LLM_TEMP = 0.3
PC_HOST = os.getenv("PCIP")
MODEL = "gpt-oss:20b"
WAKE_WORD = "right"
VOSK_MODEL_PATH = "/home/samol/vosk-model/vosk-model-small-en-us-0.15"
PIPER_MODEL = "/home/samol/Desktop/en_US-lessac-medium.onnx"

logging.getLogger("duckduckgo_search").setLevel(logging.CRITICAL)
console = Console()
audio_q = queue.Queue(maxsize=10)
chat_history = [{"role": "system", "content": "You are Pip. Use web_search for news. Be concise."}]

ui_state = {
    "status": "Idle (Waiting for 'Right')",
    "partial": "",
    "color": "cyan",
    "cpu_temp": "00.0"
}

# --- 2. SYSTEM HELPERS ---
def get_pi_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.read()) / 1000.0
            return f"{temp:.1f}"
    except: return "N/A"

def update_system_stats():
    while True:
        ui_state["cpu_temp"] = get_pi_temp()
        time.sleep(5)

threading.Thread(target=update_system_stats, daemon=True).start()

def generate_status_panel():
    temp_val = float(ui_state["cpu_temp"]) if ui_state["cpu_temp"] != "N/A" else 0
    t_color = "green" if temp_val < 60 else "yellow" if temp_val < 75 else "red"
    
    status_text = Text.assemble(
        (f" ● ", f"bold {ui_state['color']}"),
        (f"{ui_state['status']}: ", "bold white"),
        (f"\"{ui_state['partial']}\"", "italic gray70"),
        ("\n"),
        (f" CPU TEMP: ", "bold white"),
        (f"{ui_state['cpu_temp']}°C", f"bold {t_color}"),
        (f" | LLM TEMP: ", "bold blue"),
        (f"{LLM_TEMP}", "bold white")
    )
    return Panel(status_text, border_style=ui_state['color'], title="[bold]Pip System Status")

# --- 3. THE BRAIN ---
def ask_pc(question, live_ui):
    global chat_history
    chat_history.append({"role": "user", "content": question})
    
    tools = [{
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search for news',
            'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}
        }
    }]

    try:
        payload = {
            "model": MODEL, 
            "messages": chat_history, 
            "tools": tools,
            "stream": False,
            "options": {"temperature": LLM_TEMP}
        }
        
        response = requests.post(f"{PC_HOST}/api/chat", json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        msg = data.get("message", {})
        
        if msg.get("tool_calls"):
            for tool in msg["tool_calls"]:
                query = tool['function']['arguments']['query']
                live_ui.console.print(f"[bold yellow]🔍 Searching:[/] {query}")
                with DDGS(timeout=10) as ddgs:
                    search_res = ddgs.text(query, max_results=3, backend="api")
                    search_text = " ".join([r.get('body', '') for r in search_res])
                
                chat_history.append(msg)
                chat_history.append({"role": "tool", "content": search_text})
                
                final_res = requests.post(f"{PC_HOST}/api/chat", 
                                        json={"model": MODEL, "messages": chat_history, "stream": False}, 
                                        timeout=60).json()
                msg = final_res.get("message", {})

        ans = msg.get("content", "").strip()
        chat_history.append({"role": "assistant", "content": ans})
        return ans
    except Exception as e:
        live_ui.console.print(f"[bold red]ERROR:[/] {str(e)}")
        return f"Error: {str(e)}"

def speak(text, live_ui):
    if not text: return
    clean = re.sub(r'[^a-zA-Z0-9\s.,?!]', ' ', text).strip()
    live_ui.console.print(Panel(clean, title="Pip", border_style="magenta"))
    cmd = f"echo '{clean}' | piper --model {PIPER_MODEL} --output_raw 2>/dev/null | aplay -r 22050 -f S16_LE -t raw -B 250000 -q"
    os.system(cmd)

# --- 4. MAIN ---
def main():
    try:
        vosk_model = Model(VOSK_MODEL_PATH)
        rec = KaldiRecognizer(vosk_model, 16000)
    except Exception as e:
        console.print(f"[bold red]FATAL:[/] Could not load Vosk model: {e}")
        return

    def audio_callback(indata, frames, time, status):
        audio_q.put(bytes(indata))

    with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1, callback=audio_callback):
        console.clear()
        with Live(generate_status_panel(), refresh_per_second=10) as live:
            is_active = False
            while True:
                data = audio_q.get()
                if rec.AcceptWaveform(data):
                    heard = json.loads(rec.Result()).get("text", "").lower()
                    if not heard: continue
                    
                    if not is_active and WAKE_WORD in heard:
                        is_active = True
                        ui_state.update({"status": "Listening", "color": "yellow", "partial": ""})
                        q = heard.split(WAKE_WORD)[-1].strip()
                        if q:
                            ui_state.update({"status": "Thinking", "color": "magenta", "partial": q})
                            speak(ask_pc(q, live), live)
                            is_active = False
                            ui_state.update({"status": "Idle", "color": "cyan", "partial": ""})
                    elif is_active:
                        ui_state.update({"status": "Thinking", "color": "magenta", "partial": heard})
                        speak(ask_pc(heard, live), live)
                        is_active = False
                        ui_state.update({"status": "Idle", "color": "cyan", "partial": ""})
                else:
                    ui_state["partial"] = json.loads(rec.PartialResult()).get("partial", "")
                live.update(generate_status_panel())

if __name__ == "__main__":
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        main()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)