# AI Assistant Pi

A lightweight, Python-based AI assistant designed to run on Raspberry Pi. This project integrates voice recognition, Large Language Models (LLMs), and text-to-speech to create a local, interactive hardware assistant.

## What you will need (Hardware Requirements)

    1. Raspberry Pi (Pi 4 or Pi 5 recommended)

    2. A Computer to run the local LLM

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

```
    inside each folder there is a setup.txt file that contains the setup commands
```

### 4. Install and setup Tailscale on Raspberry and PC and connect them to the same account 

Help here:
[How to install Tailscale](https://tailscale.com/docs/how-to/quickstart)

### 5. Setup Ollama on PC

Install from the official site [here](https://ollama.com/download)

#### Linux (systemd)
* Edit Service: Run 
```sudo systemctl edit ollama.service```

* Add Configuration: Add the following lines in the editor:
```
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

* Reload and Restart:
```
bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```
* Verify: ```sudo netstat -anp | grep 11434``` should show ```0.0.0.0:11434 or :::11434``` 

#### macOS
* Create LaunchAgent: Create ```~/Library/LaunchAgents/com.ollama.serve.plist```

* Add Environment Variable: Ensure the file sets ```OLLAMA_HOST``` to ```0.0.0.0```
```
<key>EnvironmentVariables</key>
<dict>
  <key>OLLAMA_HOST</key>
  <string>0.0.0.0:11434</string>
</dict>
```
* Reload: Restart the computer or load the plist with launchctl


#### Windows
* System Environment Variables: Search for "Edit system environment variables" in Windows search
* Add Variable: Click "Environment Variables," then create a new User or System variable:
```
Name: OLLAMA_HOST
Value: 0.0.0.0:11434
```
* Restart: Restart the Ollama application from the taskbar.

### 6. Create a .env file in the directory of the desired version (one pi only or independant)

Inside create a variable that looks like this:
```
PCIP = "<here place the ip of the computer from Tailscale>"
LLM = "<name of the installed model>"
```

### 7. Download the desired LLM model on the machine from the ollama application on the PC

#### Note: the name of the language model shall be changed inside of the .env file from previous step

### 8. Configure the audio interfaces
```
arecord -l  # List recording devices
aplay -l   # List playback devices
```

### 9. Enjoy

If all previous steps were a success you can leave your PC on with ollama running and start the script:

#### SoloPi
```
python solopi.py
```
#### PiDuo (with 2 raspberry pis)
##### 1. Start the second PI (The server before the PC)
```
python pi2.py
```
##### 2. Start the first PI (The one speaking with the client)
```
python pi1.py
```
#### IMPORTANT NOTE FOR RUNNING PIDUO SYSTEMS
Before starting anything you have to connect the two raspberries with a networking cable and configure the IP addresses of each raspberry to correspond to the chosen script for it:

On the raspberry running pi1.py ```192.168.0.1```

On the raspberry, running pi2.py ```192.168.0.2```
## Contributing
Contributions are welcome! If you have ideas for new features or hardware support:
- Fork the Project.

- Create your Feature Branch -  ```git checkout -b feature/AmazingFeature```

- Commit your Changes -  ```git commit -m 'Add some AmazingFeature' ```

- Push to the Branch -  ```git push origin feature/AmazingFeature```

- Open a Pull Request.
## Authors

- [@KameZh](https://github.com/KameZh)
- [@AleksTach](https://github.com/AleksTach)
- [@Kiks07](https://github.com/Kiks07Bg)


## Support

For support, you can find my email in my GitHub profile or just ask ChatGPT

