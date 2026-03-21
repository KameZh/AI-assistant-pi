from flask import Flask, request, jsonify
import ollama, requests, datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from dotenv import load_dotenv, dotenv_values 


app = Flask(__name__)
console = Console()
load_dotenv()

# --- CONFIG ---
PC_HOST = os.getenv("PCIP")
MODEL = "gpt-oss:20b"

def web_search(query: str):
    console.print(f"[bold yellow]🔍 Web Search:[/][italic] {query}[/]")
    try:
        # DuckDuckGo Abstract API
        r = requests.get(f"https://api.duckduckgo.com/?q={query}&format=json", timeout=10)
        data = r.json()
        result = data.get("AbstractText", "No abstract found. Proceeding with general knowledge.")
        return result if result else "Search yielded no summary. Check recent headlines."
    except Exception as e:
        return f"Search error: {str(e)}"

@app.route("/ask", methods=["POST"])
def ask():
    user_query = request.json.get("question")
    time_now = datetime.datetime.now().strftime("%H:%M:%S")

    # Header Table
    table = Table(title=f"Incoming Request @ {time_now}", box=None)
    table.add_column("User Question", style="cyan", justify="left")
    table.add_row(user_query)
    console.print(Panel(table, border_style="blue"))

    client = ollama.Client(host=PC_HOST)
    
    tools = [{
        'type': 'function',
        'function': {
            'name': 'web_search',
            'description': 'Search the web for real-time info, news, or current events',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'The search query'},
                },
                'required': ['query'],
            },
        },
    }]

    # 1. First Pass (Decision)
    with console.status("[bold green]Analyzing question...") as status:
        response = client.chat(
            model=MODEL,
            messages=[{'role': 'user', 'content': user_query}],
            tools=tools,
        )

        # 2. Tool Execution
        if response.message.tool_calls:
            status.update("[bold yellow]Executing Web Search...")
            for tool in response.message.tool_calls:
                if tool.function.name == 'web_search':
                    search_result = web_search(tool.function.arguments['query'])
                    
                    status.update("[bold magenta]Synthesizing final answer...")
                    final_response = client.chat(
                        model=MODEL,
                        messages=[
                            {'role': 'user', 'content': user_query},
                            response.message,
                            {'role': 'tool', 'content': search_result},
                        ],
                    )
                    ai_out = final_response.message.content
                    console.print(Panel(ai_out, title="[bold green]Final Response", border_style="green"))
                    return jsonify({"response": ai_out})

    console.print(Panel(response.message.content, title="[bold white]Direct Response", border_style="white"))
    return jsonify({"response": response.message.content})
    
# Add this to your Pi 2 (PC) script
@app.route("/clear", methods=["POST"])
def clear():
    global chat_history
    chat_history = [chat_history[0]] # Keep only the System Prompt
    return jsonify({"status": "cleared"})
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
