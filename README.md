# 💡 WiZ Smart Light Remote Widget (Linux & Windows 10/11)

A sleek, borderless, floating desktop remote control and system tray widget for Philips WiZ Connected Smart Lights. Works completely locally over Wi-Fi via UDP with zero cloud latency.

![WiZ Remote Widget](icons/bulb_on.png)

---

## 📥 Direct Download
* **[Download Latest ZIP (All-in-One)](https://github.com/rudhrahas-dev/wiz-smart-light-widget/archive/refs/heads/main.zip)**

---

## ✨ Features
* **Dual OS Support:** Fully optimized for both **Linux** (Ubuntu/Debian) and **Windows 10 / 11**.
* **Frameless Modern UI:** Borderless floating remote wand with smooth drag-and-drop.
* **Dual Orientation:** Click `⇄` to switch between a **Vertical Remote Wand** and a **Horizontal Floating Strip**.
* **System Tray Integration (pystray):**
  * Live status icon in the tray: 💡 ON, ⏻ OFF, 🔴 Offline.
  * Quick right-click controls for Power, Presets, and Brightness.
  * Minimize to tray anytime (`📥` or `✕`).
* **Presets & CCT Color Temperature:**
  * ☀️ Daylight (6500K)
  * ❄️ Cool Blue (6500K)
  * 📖 Study / Focus (5000K)
  * ☕ Warm White (3500K)
  * 🕯️ Candlelight (3000K)
  * 🌙 Night Light (3000K)
* **Always-on-Top:** Click the `📌` pin icon to float above games or workspaces.
* **Auto-Discovery:** Automatically discovers bulb IP shifts via local UDP broadcasts if DHCP leases change.

---

## 🪟 Windows 10 / 11 Setup

1. **Install Python:**
   * Download Python from [python.org](https://www.python.org/downloads/).
   * ⚠️ Check **"Add Python to PATH"** during installation.
2. **Run:**
   * Connect to the same Wi-Fi as your WiZ bulb.
   * Double-click **`run_windows.bat`**.
   * It will automatically install `Pillow` and `pystray` and start the widget silently without any command prompt window.
3. *(Optional)* **Run at Windows Startup:**
   * Press `Win + R`, type `shell:startup`, and press Enter.
   * Create a shortcut to `widget.pyw` and place it in that folder.

---

## 🐧 Linux Setup

1. **Install Dependencies:**
   ```bash
   sudo apt update
   sudo apt install -y python3-pil python3-pil.imagetk python3-pystray
   ```
2. **Run:**
   ```bash
   python3 widget.py
   ```
3. *(Optional)* **Desktop Application Shortcut:**
   * Copy `WiZ Smart Light.desktop` to `~/.local/share/applications/`:
   ```bash
   cp "WiZ Smart Light.desktop" ~/.local/share/applications/
   ```

---

## ⚙️ Configuration
Click the `⚙️` gear icon on the remote to configure:
* **Bulb IP Address** (Default will auto-discover).
* **WiZ UDP Signing Key** (Optional for newer Pro firmware).

Config is saved at:
* **Windows:** `%APPDATA%\wiz_widget\config.json`
* **Linux:** `~/.config/wiz_widget/config.json`

---

## 📄 License
MIT License.
