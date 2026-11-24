# WiZ Smart Light Widget for Windows 10 / 11

A sleek, borderless, floating desktop remote control and tray widget for your Philips WiZ Smart Light.

---

## 🚀 Quick Setup (3 Steps)

### Step 1: Ensure Python is Installed
1. If you don't have Python, download and install Python from: **https://www.python.org/downloads/**
2. ⚠️ **IMPORTANT**: During installation, check the box that says:
   `☑ Add Python to PATH`

### Step 2: Make Sure Your Laptop is on the Same Wi-Fi
* Connect your Windows 10 laptop to the same Wi-Fi network as the bulb (e.g. `S02_Home_Control`).

### Step 3: Run the Widget
* Simply **double-click** `run_windows.bat`.
* On the first run, it will automatically install the two lightweight dependencies (`Pillow` and `pystray`), then launch the widget seamlessly without any black console window.
* Subsequent runs can be launched either by double-clicking `run_windows.bat` or directly double-clicking `widget.pyw`.

---

## 💡 Features & Controls
* **Drag & Move:** Click and drag the grip icon (`⋮⋮` or `⠿`) to place the remote wand anywhere on your desktop.
* **Toggle Orientation:** Click the `⇄` button to switch between a **Vertical Remote Wand** and a **Horizontal Floating Strip**.
* **Always on Top:** Click the `📌` pin icon to keep the widget floating above all other windows.
* **Minimize to Tray:** Click `📥` or `✕` to hide the remote to the Windows System Tray (next to the clock).
* **Presets & Brightness:** Click the preset icons (☀️ Daylight, ❄️ Cool Blue, 📖 Study, ☕ Warm White, 🕯️ Candlelight, 🌙 Night Light) or click the brightness percentage to cycle levels.
* **Settings:** Click `⚙️` to adjust the Bulb IP address or signing key if needed.

---

## 🔄 Optional: Start Automatically with Windows
If you want the remote widget to launch automatically when you turn on your laptop:
1. Press `Win + R` on your keyboard, type:
   ```text
   shell:startup
   ```
   and press Enter. (This opens your Windows Startup folder).
2. Right-click `widget.pyw` (or `run_windows.bat`), choose **Create shortcut**.
3. Move that shortcut into the Startup folder.
