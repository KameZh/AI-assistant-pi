# AI Assistant Pi

A lightweight, Python-based AI assistant designed to run on a Raspberry Pi. This project integrates voice recognition (Vosk & Whisper), Large Language Models (LLMs), and text-to-speech (Piper) to create a local, interactive hardware assistant.

## What you will need (Hardware Requirements)

    1. Raspberry Pi (Pi 4 or Pi 5 recommended)
    2. A Computer to run the local LLM (for SoloPi) or a second Raspberry Pi (for PiDuo)
    3. USB Microphone or a Respeaker HAT
    4. Speaker (USB, 3.5mm jack, or Bluetooth)
    5. MicroSD Card (16GB+ with Raspberry Pi OS installed)
    6. Stable Internet Connection

## Run Locally

### 1. Clone the project on the Raspberry PI

```bash
  git clone https://github.com/KameZh/AI-assistant-pi.git
```

### 2. Go to the project directory

```bash
  cd AI-assistant-pi
```

### 3. Install dependencies

First, install the required system audio drivers. Without these, the Python audio libraries will crash:
```bash
sudo apt update
sudo apt install -y libportaudio2 portaudio19-dev
```

Next, check the `setup.txt` file inside your specific version folder for the Python requirements. Activate your virtual environment and install them:
```bash
pip install -r requirements.txt
```

#### Manual Piper TTS Installation (Crucial for Raspberry Pi)
Raspberry Pi architecture requires the raw Piper binary to work correctly. Run these commands inside your project folder:
```bash
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
tar -xf piper_linux_aarch64.tar.gz
rm piper_linux_aarch64.tar.gz
```
*(Ensure your `.onnx` voice models and Vosk models are downloaded and their paths are updated in your script).*

### 4. Install and setup Tailscale on Raspberry and PC
Connect both devices to the same Tailscale account to create a secure, encrypted tunnel.
Help here: [How to install Tailscale](https://tailscale.com/docs/how-to/quickstart)

### 5. Setup Ollama on PC (The "Brain")

Install from the official site [here](https://ollama.com/download)

#### Linux (systemd)
* Edit Service: Run 
```bash
sudo systemctl edit ollama.service
```

* Add Configuration: Add the following lines in the editor:
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

* Reload and Restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```
* Verify: `sudo netstat -anp | grep 11434` should show `0.0.0.0:11434` or `:::11434` 

#### macOS
* Create LaunchAgent: Create `~/Library/LaunchAgents/com.ollama.serve.plist`

* Add Environment Variable: Ensure the file sets `OLLAMA_HOST` to `0.0.0.0`
```xml
<key>EnvironmentVariables</key>
<dict>
  <key>OLLAMA_HOST</key>
  <string>0.0.0.0:11434</string>
</dict>
```
* Reload: Restart the computer or load the plist with `launchctl`


#### Windows
* System Environment Variables: Search for "Edit system environment variables" in Windows search
* Add Variable: Click "Environment Variables," then create a new User or System variable:
```text
Name: OLLAMA_HOST
Value: 0.0.0.0:11434
```
* Restart: Completely close the Ollama application from the system tray and open it again.

### 6. Configure the Scripts

Open your Python script (`solopi.py` for SoloPi, or the respective PiDuo scripts) and edit the configuration variables at the top of the file. You must manually insert your PC's Tailscale IP address and the exact name of your chosen LLM:

```python
PC_TAILSCALE_IP = "100.X.X.X"  # Replace with your PC's Tailscale IP
AI_MODEL = "gemma4:e2b"        # Replace with your downloaded model name
```

### 7. Download the desired LLM model on the PC
Open your PC's terminal or command prompt and pull the model you specified in the previous step:
```bash
ollama run gemma4:e2b
```

### 8. Configure the Audio Interfaces (ALSA Routing)
Linux audio routing can fail or cause silent errors (Error 524). You must explicitly find your hardware addresses:

```bash
arecord -l   # List recording devices (Microphone)
aplay -l     # List playback devices (Headphones/Speakers)
```
Note the **Card** and **Device** numbers for your preferred speaker (e.g., `card 2, device 0`). Update the `aplay` command in your script to use that exact hardware route (e.g., `aplay -D plughw:2,0`).

### 9. Enjoy

If all previous steps were a success, leave your PC on with Ollama running and start the script. *(Note: The SoloPi script will ask you to select a language at startup to prevent transcription hallucinations).*

#### SoloPi
```bash
python solopi.py
```

#### PiDuo (with 2 Raspberry Pis)
##### 1. Start the second PI (The server before the PC)
```bash
python pi2.py
```
##### 2. Start the first PI (The one speaking with the client)
```bash
python pi1.py
```
#### IMPORTANT NOTE FOR RUNNING PIDUO SYSTEMS
Before starting anything you have to connect the two raspberries with a networking cable and configure the IP addresses of each raspberry to correspond to the chosen script for it:

On the raspberry running pi1.py: `192.168.0.1`

On the raspberry running pi2.py: `192.168.0.2`

## Contributing
Contributions are welcome! If you have ideas for new features or hardware support:
- Fork the Project.
- Create your Feature Branch -  `git checkout -b feature/AmazingFeature`
- Commit your Changes -  `git commit -m 'Add some AmazingFeature'`
- Push to the Branch -  `git push origin feature/AmazingFeature`
- Open a Pull Request.

## Authors

- [@KameZh](https://github.com/KameZh)
- [@AleksTach](https://github.com/AleksTach)
- [@Kiks07](https://github.com/Kiks07Bg)

## Support

For support, you can find my email in my GitHub profile or just ask Gemini.
