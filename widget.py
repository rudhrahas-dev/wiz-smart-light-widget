#!/usr/bin/env python3
"""
WiZ Smart Light - Floating Thin Strip Remote Widget with Top Tray Support
========================================================================
A sleek, borderless desktop remote control for WiZ smart lights:
  - Frameless (no window manager title bars or borders)
  - All-icon interface with rich, dynamic floating tooltips
  - Dual Orientation: Vertical Remote Wand ↔ Horizontal Floating Strip
  - Top Bar Tray Integration (pystray):
      * Minimise to system tray with live bulb state icon (💡 ON, ⏻ OFF, 🔴 Offline)
      * Quick tray controls for Power, Presets, and Brightness
      * Restore / Hide remote wand anytime from tray
  - Instant optimistic feedback and background UDP state synchronization
"""

import os
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Dict, Any, Callable, Tuple

from PIL import Image
import pystray
from pystray import MenuItem as item, Menu

from bulb_controller import WizBulbController

IS_WIN = sys.platform == "win32"
FONT_MAIN = "Segoe UI" if IS_WIN else "DejaVu Sans"
FONT_EMOJI = "Segoe UI Emoji"

if IS_WIN:
    # Enable high-DPI scaling on Windows 10/11
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "wiz_widget")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/wiz_widget")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

# Visual Palette (Matches dark theme)
BG_DARK = "#121316"
BG_CARD = "#1a1c24"
BG_HOVER = "#242735"
BORDER_COLOR = "#2d3142"

ACCENT_CYAN = "#00cec9"
ACCENT_GREEN = "#2ecc71"
ACCENT_GOLD = "#fbbf24"        # Warm amber for light ON
ACCENT_RED = "#e74c3c"
ACCENT_BLUE = "#38bdf8"
TEXT_WHITE = "#f5f6fa"
TEXT_MUTED = "#8e9297"
TEXT_DIM = "#57606f"

# Preset definitions for scheduled automations
SCHEDULE_PRESETS: Dict[str, Dict[str, Any]] = {
    "💡 Turn Light ON": {"action": "turn_on"},
    "⏻ Turn Light OFF": {"action": "turn_off"},
    "☀️ Daylight (6500K, 100%)": {"action": "preset", "temp": 6500, "dim": 100},
    "❄️ Cool Blue (6500K, 100%)": {"action": "preset", "temp": 6500, "dim": 100},
    "📖 Study / Focus (5000K, 100%)": {"action": "preset", "temp": 5000, "dim": 100},
    "☕ Warm White (3500K, 80%)": {"action": "preset", "temp": 3500, "dim": 80},
    "🕯️ Candlelight (3000K, 30%)": {"action": "preset", "temp": 3000, "dim": 30},
    "🌙 Night Light (3000K, 10%)": {"action": "preset", "temp": 3000, "dim": 10},
}


def load_config() -> Dict[str, Any]:
    default_config = {
        "ip": "192.168.0.101",
        "signing_key": "",
        "always_on_top": True,
        "orientation": "vertical",     # "vertical" or "horizontal"
        "win_x": -1,
        "win_y": -1,
        "poll_interval": 3.0,
        "schedules": []
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                default_config.update(data)
        except Exception:
            pass
    return default_config


def save_config(config: Dict[str, Any]) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)


def kelvin_to_rgb_hex(temp: int) -> str:
    """Map Kelvin (3000K - 6500K) to hex color from warm amber to cool blue."""
    t = max(3000, min(6500, int(temp)))
    factor = (t - 3000) / (6500 - 3000)
    if factor < 0.5:
        sub = factor / 0.5
        r = 255
        g = int(170 + (255 - 170) * sub)
        b = int(70 + (255 - 70) * sub)
    else:
        sub = (factor - 0.5) / 0.5
        r = int(255 - (255 - 200) * sub)
        g = int(255 - (255 - 226) * sub)
        b = 255
    return f"#{r:02x}{g:02x}{b:02x}"


class ToolTip:
    """Floating modern dark tooltip for icons."""
    def __init__(self, widget: tk.Widget, text_or_func):
        self.widget = widget
        self.text_or_func = text_or_func
        self.tip_window = None
        self.after_id = None

        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def schedule_show(self, event=None):
        self.hide()
        self.after_id = self.widget.after(350, self.show)

    def show(self):
        if self.tip_window or not self.widget.winfo_exists():
            return

        text = self.text_or_func() if callable(self.text_or_func) else self.text_or_func
        if not text:
            return

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)

        frame = tk.Frame(tw, bg=BORDER_COLOR, bd=1)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl = tk.Label(frame, text=text, justify=tk.LEFT,
                       background=BG_CARD, foreground=TEXT_WHITE,
                       font=(FONT_MAIN, 8), padx=7, pady=4)
        lbl.pack()

        tw.update_idletasks()
        tip_w = tw.winfo_width()
        tip_h = tw.winfo_height()

        wx = self.widget.winfo_rootx()
        wy = self.widget.winfo_rooty()
        ww = self.widget.winfo_width()
        wh = self.widget.winfo_height()

        screen_w = self.widget.winfo_screenwidth()
        screen_h = self.widget.winfo_screenheight()

        parent_w = self.widget.winfo_toplevel().winfo_width()
        parent_h = self.widget.winfo_toplevel().winfo_height()
        is_horizontal = parent_w > parent_h

        if is_horizontal:
            x = wx + (ww - tip_w) // 2
            x = max(10, min(screen_w - tip_w - 10, x))
            if wy + wh + tip_h + 10 > screen_h:
                y = wy - tip_h - 6
            else:
                y = wy + wh + 6
        else:
            if wx + ww + tip_w + 12 > screen_w:
                x = wx - tip_w - 6
            else:
                x = wx + ww + 6
            y = wy + (wh - tip_h) // 2
            y = max(10, min(screen_h - tip_h - 10, y))

        tw.wm_geometry(f"+{x}+{y}")

    def hide(self, event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class SettingsDialog(tk.Toplevel):
    """Frameless dark modal dialog for configuring bulb IP and security key."""
    def __init__(self, parent: tk.Tk, config: Dict[str, Any], on_save_cb: Callable[[str, str], None]):
        super().__init__(parent)
        self.config = config
        self.on_save_cb = on_save_cb
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=BORDER_COLOR)

        box = tk.Frame(self, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=14, pady=12)
        box.pack(fill=tk.BOTH, expand=True)

        hdr = tk.Frame(box, bg=BG_DARK)
        hdr.pack(fill=tk.X, pady=(0, 10))
        tk.Label(hdr, text="⚙️ WiZ Bulb Configuration", font=(FONT_MAIN, 9, "bold"), fg=ACCENT_CYAN, bg=BG_DARK).pack(side=tk.LEFT)
        btn_x = tk.Label(hdr, text="✕", font=(FONT_MAIN, 10), fg=TEXT_MUTED, bg=BG_DARK, cursor="hand2")
        btn_x.pack(side=tk.RIGHT)
        btn_x.bind("<Button-1>", lambda e: self.destroy())
        btn_x.bind("<Enter>", lambda e: btn_x.config(fg=ACCENT_RED))
        btn_x.bind("<Leave>", lambda e: btn_x.config(fg=TEXT_MUTED))

        tk.Label(box, text="Bulb IP Address:", font=(FONT_MAIN, 8), fg=TEXT_MUTED, bg=BG_DARK).pack(anchor="w")
        self.ent_ip = tk.Entry(box, bg=BG_CARD, fg=TEXT_WHITE, insertbackground=TEXT_WHITE, bd=1, relief=tk.FLAT, font=(FONT_MAIN, 9))
        self.ent_ip.insert(0, self.config.get("ip", "192.168.0.101"))
        self.ent_ip.pack(fill=tk.X, pady=(2, 8))

        tk.Label(box, text="WiZ UDP Signing Key (Optional hex):", font=(FONT_MAIN, 8), fg=TEXT_MUTED, bg=BG_DARK).pack(anchor="w")
        self.ent_key = tk.Entry(box, bg=BG_CARD, fg=TEXT_WHITE, insertbackground=TEXT_WHITE, bd=1, relief=tk.FLAT, font=(FONT_MAIN, 9))
        self.ent_key.insert(0, self.config.get("signing_key", ""))
        self.ent_key.pack(fill=tk.X, pady=(2, 10))

        btn_box = tk.Frame(box, bg=BG_DARK)
        btn_box.pack(fill=tk.X)

        btn_save = tk.Label(btn_box, text="Save & Connect", font=(FONT_MAIN, 8, "bold"),
                            bg=ACCENT_CYAN, fg=BG_DARK, padx=10, pady=4, cursor="hand2")
        btn_save.pack(side=tk.LEFT)
        btn_save.bind("<Button-1>", lambda e: self._save())
        btn_save.bind("<Enter>", lambda e: btn_save.config(bg="#38bdf8"))
        btn_save.bind("<Leave>", lambda e: btn_save.config(bg=ACCENT_CYAN))

        btn_cancel = tk.Label(btn_box, text="Cancel", font=(FONT_MAIN, 8),
                              bg=BG_CARD, fg=TEXT_MUTED, padx=8, pady=4, cursor="hand2")
        btn_cancel.pack(side=tk.RIGHT)
        btn_cancel.bind("<Button-1>", lambda e: self.destroy())

        self.update_idletasks()
        pw_x = parent.winfo_rootx()
        pw_y = parent.winfo_rooty()
        self.geometry(f"290x190+{max(10, pw_x - 300)}+{max(10, pw_y)}")

    def _save(self):
        new_ip = self.ent_ip.get().strip()
        new_key = self.ent_key.get().strip()
        self.on_save_cb(new_ip, new_key)
        self.destroy()


class ScheduleDialog(tk.Toplevel):
    """Frameless dark modal dialog for configuring automated schedules and timers."""
    def __init__(self, parent: "WizFloatingWidget", config: Dict[str, Any], on_schedules_updated: Callable[[list], None]):
        super().__init__(parent)
        self.parent_widget = parent
        self.config = config
        self.on_schedules_updated = on_schedules_updated
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(bg=BORDER_COLOR)

        self.box = tk.Frame(self, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=14, pady=12)
        self.box.pack(fill=tk.BOTH, expand=True)

        # Header
        hdr = tk.Frame(self.box, bg=BG_DARK)
        hdr.pack(fill=tk.X, pady=(0, 8))
        tk.Label(hdr, text="⏰ Schedules & Automation", font=(FONT_MAIN, 10, "bold"), fg=ACCENT_GOLD, bg=BG_DARK).pack(side=tk.LEFT)
        btn_x = tk.Label(hdr, text="✕", font=(FONT_MAIN, 10), fg=TEXT_MUTED, bg=BG_DARK, cursor="hand2")
        btn_x.pack(side=tk.RIGHT)
        btn_x.bind("<Button-1>", lambda e: self.destroy())
        btn_x.bind("<Enter>", lambda e: btn_x.config(fg=ACCENT_RED))
        btn_x.bind("<Leave>", lambda e: btn_x.config(fg=TEXT_MUTED))

        # Active Rules Container
        lbl_list = tk.Label(self.box, text="Active Timed Schedules:", font=(FONT_MAIN, 8, "bold"), fg=TEXT_MUTED, bg=BG_DARK)
        lbl_list.pack(anchor="w", pady=(2, 4))

        list_container = tk.Frame(self.box, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.canvas = tk.Canvas(list_container, bg=BG_CARD, highlightthickness=0, height=140)
        scrollbar = tk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=BG_CARD)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._render_schedules()

        # Add Rule Form
        add_box = tk.LabelFrame(self.box, text="Add New Timing Rule", font=(FONT_MAIN, 8, "bold"),
                                fg=ACCENT_CYAN, bg=BG_DARK, bd=1, relief=tk.SOLID, padx=8, pady=8)
        add_box.pack(fill=tk.X, pady=(0, 6))

        # Row 1: Time & Repeat
        r1 = tk.Frame(add_box, bg=BG_DARK)
        r1.pack(fill=tk.X, pady=2)
        tk.Label(r1, text="Time:", font=(FONT_MAIN, 8), fg=TEXT_WHITE, bg=BG_DARK).pack(side=tk.LEFT, padx=(0, 4))
        
        self.hr_var = tk.StringVar(value="08")
        hr_menu = tk.OptionMenu(r1, self.hr_var, *[f"{h:02d}" for h in range(24)])
        hr_menu.config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8), bd=1, relief=tk.FLAT, highlightthickness=0, width=3)
        hr_menu["menu"].config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8))
        hr_menu.pack(side=tk.LEFT, padx=(0, 2))

        tk.Label(r1, text=":", font=(FONT_MAIN, 9, "bold"), fg=TEXT_WHITE, bg=BG_DARK).pack(side=tk.LEFT, padx=1)

        self.min_var = tk.StringVar(value="00")
        min_menu = tk.OptionMenu(r1, self.min_var, *[f"{m:02d}" for m in range(0, 60, 5)])
        min_menu.config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8), bd=1, relief=tk.FLAT, highlightthickness=0, width=3)
        min_menu["menu"].config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8))
        min_menu.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(r1, text="Repeat:", font=(FONT_MAIN, 8), fg=TEXT_WHITE, bg=BG_DARK).pack(side=tk.LEFT, padx=(0, 4))
        self.repeat_var = tk.StringVar(value="Everyday")
        rep_menu = tk.OptionMenu(r1, self.repeat_var, "Everyday", "Weekdays (Mon-Fri)", "Weekends (Sat-Sun)")
        rep_menu.config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8), bd=1, relief=tk.FLAT, highlightthickness=0)
        rep_menu["menu"].config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8))
        rep_menu.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Row 2: Action
        r2 = tk.Frame(add_box, bg=BG_DARK)
        r2.pack(fill=tk.X, pady=(6, 4))
        tk.Label(r2, text="Action:", font=(FONT_MAIN, 8), fg=TEXT_WHITE, bg=BG_DARK).pack(side=tk.LEFT, padx=(0, 4))

        self.action_keys = list(SCHEDULE_PRESETS.keys())
        self.action_var = tk.StringVar(value=self.action_keys[0])
        act_menu = tk.OptionMenu(r2, self.action_var, *self.action_keys)
        act_menu.config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8), bd=1, relief=tk.FLAT, highlightthickness=0)
        act_menu["menu"].config(bg=BG_CARD, fg=TEXT_WHITE, font=(FONT_MAIN, 8))
        act_menu.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Add Button
        btn_add = tk.Label(add_box, text="+ Add This Schedule", font=(FONT_MAIN, 8, "bold"),
                           bg=ACCENT_CYAN, fg=BG_DARK, padx=10, pady=5, cursor="hand2")
        btn_add.pack(fill=tk.X, pady=(6, 2))
        btn_add.bind("<Button-1>", lambda e: self._add_schedule())
        btn_add.bind("<Enter>", lambda e: btn_add.config(bg="#38bdf8"))
        btn_add.bind("<Leave>", lambda e: btn_add.config(bg=ACCENT_CYAN))

        # Bottom row: Close
        btn_close = tk.Label(self.box, text="Done / Close", font=(FONT_MAIN, 8),
                             bg=BG_CARD, fg=TEXT_MUTED, padx=10, pady=4, cursor="hand2")
        btn_close.pack(anchor="e")
        btn_close.bind("<Button-1>", lambda e: self.destroy())

        self.update_idletasks()
        pw_x = parent.winfo_rootx()
        pw_y = parent.winfo_rooty()
        self.geometry(f"360x420+{max(10, pw_x - 370)}+{max(10, pw_y)}")

    def _render_schedules(self):
        for w in self.scrollable_frame.winfo_children():
            w.destroy()

        schedules = self.config.get("schedules", [])
        if not schedules:
            empty_lbl = tk.Label(self.scrollable_frame, text="No timed rules yet.\nAdd a timing rule below to automate your light!",
                                 font=(FONT_MAIN, 8), fg=TEXT_MUTED, bg=BG_CARD, pady=24)
            empty_lbl.pack(fill=tk.BOTH, expand=True)
            return

        for idx, sch in enumerate(schedules):
            row = tk.Frame(self.scrollable_frame, bg=BG_CARD, pady=4, padx=6)
            row.pack(fill=tk.X, expand=True, pady=1)

            enabled = sch.get("enabled", True)
            btn_toggle = tk.Label(row, text="● ON" if enabled else "○ OFF",
                                  font=(FONT_MAIN, 8, "bold"),
                                  fg=ACCENT_GREEN if enabled else TEXT_DIM,
                                  bg=BG_CARD, cursor="hand2", width=6, anchor="w")
            btn_toggle.pack(side=tk.LEFT, padx=(0, 6))
            btn_toggle.bind("<Button-1>", lambda e, i=idx: self._toggle_schedule(i))
            ToolTip(btn_toggle, "Click to Enable / Disable this rule")

            # Time badge
            lbl_time = tk.Label(row, text=sch.get("time", "00:00"), font=(FONT_MAIN, 9, "bold"),
                                fg=ACCENT_GOLD if enabled else TEXT_DIM, bg=BG_CARD)
            lbl_time.pack(side=tk.LEFT, padx=(0, 6))

            # Action & Repeat
            info_text = f"{sch.get('name', 'Action')} • {sch.get('repeat', 'Everyday')}"
            lbl_info = tk.Label(row, text=info_text, font=(FONT_MAIN, 8),
                                fg=TEXT_WHITE if enabled else TEXT_DIM, bg=BG_CARD, anchor="w")
            lbl_info.pack(side=tk.LEFT, fill=tk.X, expand=True)

            btn_del = tk.Label(row, text="✕", font=(FONT_MAIN, 9, "bold"),
                               fg=TEXT_MUTED, bg=BG_CARD, cursor="hand2", padx=6)
            btn_del.pack(side=tk.RIGHT)
            btn_del.bind("<Button-1>", lambda e, i=idx: self._delete_schedule(i))
            btn_del.bind("<Enter>", lambda e, b=btn_del: b.config(fg=ACCENT_RED))
            btn_del.bind("<Leave>", lambda e, b=btn_del: b.config(fg=TEXT_MUTED))
            ToolTip(btn_del, "Delete this schedule")

    def _add_schedule(self):
        t_str = f"{self.hr_var.get()}:{self.min_var.get()}"
        act_name = self.action_var.get()
        act_info = SCHEDULE_PRESETS.get(act_name, {"action": "turn_on"})
        repeat = self.repeat_var.get()

        new_entry = {
            "id": f"sch_{int(time.time() * 1000)}",
            "enabled": True,
            "time": t_str,
            "name": act_name,
            "repeat": repeat,
            **act_info
        }

        schedules = self.config.get("schedules", [])
        schedules.append(new_entry)
        schedules.sort(key=lambda s: s.get("time", "00:00"))
        self.config["schedules"] = schedules
        self.on_schedules_updated(schedules)
        self._render_schedules()

    def _toggle_schedule(self, idx: int):
        schedules = self.config.get("schedules", [])
        if 0 <= idx < len(schedules):
            schedules[idx]["enabled"] = not schedules[idx].get("enabled", True)
            self.config["schedules"] = schedules
            self.on_schedules_updated(schedules)
            self._render_schedules()

    def _delete_schedule(self, idx: int):
        schedules = self.config.get("schedules", [])
        if 0 <= idx < len(schedules):
            schedules.pop(idx)
            self.config["schedules"] = schedules
            self.on_schedules_updated(schedules)
            self._render_schedules()


class WizFloatingWidget(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.controller = WizBulbController(
            ip=self.config.get("ip", "192.168.0.101"),
            signing_key=self.config.get("signing_key", "")
        )

        self.bulb_state: Dict[str, Any] = {
            "online": False,
            "state": False,
            "dimming": 85,
            "temp": 6500,
            "rssi": 0
        }
        self.orientation = self.config.get("orientation", "vertical")
        self.polling_active = True
        self.is_minimized = False
        self.settings_dialog: Optional[SettingsDialog] = None
        self.schedule_dialog: Optional[ScheduleDialog] = None

        # Drag tracking
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._orig_win_x = 0
        self._orig_win_y = 0

        self._setup_window()
        self._load_tray_icons()
        self._build_ui()
        self._apply_geometry()
        self._setup_tray()
        self._start_background_polling()
        self._start_scheduler()

        # Immediate bulb state query
        self.after(50, self.refresh_state_async)

    def _setup_window(self):
        self.title("WiZ Remote")
        self.overrideredirect(True)
        self.wm_attributes("-topmost", self.config.get("always_on_top", True))
        self.configure(bg=BORDER_COLOR)

    def _load_tray_icons(self):
        self.tray_icons = {}
        for state in ["on", "off", "offline"]:
            path = os.path.join(ICON_DIR, f"bulb_{state}.png")
            if os.path.exists(path):
                self.tray_icons[state] = Image.open(path)
            else:
                self.tray_icons[state] = Image.new("RGBA", (32, 32), (200, 150, 0, 255))

    def _setup_tray(self):
        current_img = self.tray_icons.get("off", Image.new("RGBA", (32, 32), (100, 100, 100, 255)))
        self.tray_icon = pystray.Icon(
            "wiz_smart_light",
            current_img,
            "WiZ Smart Light",
            menu=self._create_tray_menu()
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _get_tray_status_label(self) -> str:
        online = self.bulb_state.get("online", False)
        if not online:
            return "WiZ Bulb: Offline"
        is_on = self.bulb_state.get("state", False)
        dim = self.bulb_state.get("dimming", 85)
        return f"WiZ Bulb: {'💡 ON' if is_on else '⏻ OFF'} ({dim}%)"

    def _create_tray_menu(self):
        return Menu(
            item(lambda text: self._get_tray_status_label(), None, enabled=False),
            Menu.SEPARATOR,
            item(
                lambda text: "Turn Light OFF 💡" if self.bulb_state.get("state", False) else "Turn Light ON ⏻",
                lambda i, it: self.after(0, self.toggle_power)
            ),
            item(
                "Presets",
                Menu(
                    item("☀️ Daylight (6500K)", lambda i, it: self.after(0, lambda: self.apply_preset(6500, 100))),
                    item("❄️ Cool Blue (6500K)", lambda i, it: self.after(0, lambda: self.apply_preset(6500, 100))),
                    item("📖 Study / Focus (5000K)", lambda i, it: self.after(0, lambda: self.apply_preset(5000, 100))),
                    item("☕ Warm White (3500K)", lambda i, it: self.after(0, lambda: self.apply_preset(3500, 80))),
                    item("🕯️ Candlelight (3000K)", lambda i, it: self.after(0, lambda: self.apply_preset(3000, 30))),
                    item("🌙 Night Light (3000K)", lambda i, it: self.after(0, lambda: self.apply_preset(3000, 10))),
                )
            ),
            item(
                "Brightness",
                Menu(
                    item("100%", lambda i, it: self.after(0, lambda: self.set_dimming(100))),
                    item("75%", lambda i, it: self.after(0, lambda: self.set_dimming(75))),
                    item("50%", lambda i, it: self.after(0, lambda: self.set_dimming(50))),
                    item("25%", lambda i, it: self.after(0, lambda: self.set_dimming(25))),
                    item("10%", lambda i, it: self.after(0, lambda: self.set_dimming(10))),
                )
            ),
            item("⏰ Schedules & Timers...", lambda i, it: self.after(0, self.open_schedules)),
            Menu.SEPARATOR,
            item(
                lambda text: "🖥️ Show Remote Wand" if self.is_minimized else "📥 Hide Remote to Tray",
                lambda i, it: self.after(0, self.toggle_remote_visibility),
                default=True
            ),
            Menu.SEPARATOR,
            item("✕ Quit WiZ Remote", lambda i, it: self.after(0, self.quit_app))
        )

    def _apply_geometry(self, target_x: Optional[int] = None, target_y: Optional[int] = None):
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        if self.orientation == "vertical":
            w = 42
            h = 428
        else:
            w = 462
            h = 36

        if target_x is not None and target_y is not None:
            x = target_x
            y = target_y
        else:
            cfg_x = self.config.get("win_x", -1)
            cfg_y = self.config.get("win_y", -1)
            if cfg_x >= 0 and cfg_y >= 0:
                x = cfg_x
                y = cfg_y
            else:
                x = screen_w - w - 60
                y = 130

        x = max(0, min(screen_w - w, x))
        y = max(0, min(screen_h - h, y))

        self.geometry(f"{w}x{h}+{x}+{y}")

    def _start_drag(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._orig_win_x = self.winfo_x()
        self._orig_win_y = self.winfo_y()

    def _do_drag(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        new_x = self._orig_win_x + dx
        new_y = self._orig_win_y + dy
        self.geometry(f"+{new_x}+{new_y}")
        self.config["win_x"] = new_x
        self.config["win_y"] = new_y

    def _save_position_on_release(self, event):
        save_config(self.config)

    def _build_ui(self):
        for w in self.winfo_children():
            w.destroy()

        self.container = tk.Frame(self, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        self.container.bind("<ButtonPress-1>", self._start_drag)
        self.container.bind("<B1-Motion>", self._do_drag)
        self.container.bind("<ButtonRelease-1>", self._save_position_on_release)

        is_v = (self.orientation == "vertical")
        side_pack = tk.TOP if is_v else tk.LEFT

        def make_icon_btn(parent, text, cmd, font=(FONT_MAIN, 10), fg=TEXT_WHITE, bg=BG_CARD, active_bg=BG_HOVER):
            btn = tk.Label(parent, text=text, font=font, fg=fg, bg=bg, cursor="hand2")
            btn.bind("<Button-1>", lambda e: cmd())
            btn.bind("<Enter>", lambda e: btn.config(bg=active_bg))
            btn.bind("<Leave>", lambda e: btn.config(bg=bg))
            return btn

        # 1. Grip / Drag Handle
        grip = tk.Label(self.container, text="⋮⋮" if is_v else "⠿", font=(FONT_MAIN, 9, "bold"),
                        fg=TEXT_MUTED, bg=BG_DARK, cursor="fleur")
        grip.pack(side=side_pack, padx=3 if not is_v else 0, pady=3 if is_v else 0)
        grip.bind("<ButtonPress-1>", self._start_drag)
        grip.bind("<B1-Motion>", self._do_drag)
        grip.bind("<ButtonRelease-1>", self._save_position_on_release)
        ToolTip(grip, "Drag to move remote wand")

        # 2. Status Dot
        self.lbl_status = tk.Label(self.container, text="●", font=(FONT_MAIN, 9),
                                   fg=ACCENT_GREEN if self.bulb_state["online"] else ACCENT_RED,
                                   bg=BG_DARK)
        self.lbl_status.pack(side=side_pack, padx=3 if not is_v else 0, pady=2 if is_v else 0)
        ToolTip(self.lbl_status, self._get_status_tooltip)

        # 3. Hero Power Button
        is_on = self.bulb_state.get("state", False)
        self.btn_power = tk.Label(
            self.container,
            text="💡" if is_on else "⏻",
            font=("Segoe UI Emoji", 12),
            fg="#121316" if is_on else TEXT_MUTED,
            bg=ACCENT_GOLD if is_on else BG_CARD,
            padx=5, pady=3, cursor="hand2"
        )
        self.btn_power.pack(side=side_pack, padx=2, pady=2)
        self.btn_power.bind("<Button-1>", lambda e: self.toggle_power())
        self.btn_power.bind("<Enter>", lambda e: self.btn_power.config(bg="#f59e0b" if self.bulb_state.get("state", False) else BG_HOVER))
        self.btn_power.bind("<Leave>", lambda e: self.btn_power.config(bg=ACCENT_GOLD if self.bulb_state.get("state", False) else BG_CARD))
        ToolTip(self.btn_power, lambda: "💡 Light is ON (Click to turn OFF)" if self.bulb_state.get("state", False) else "⏻ Light is OFF (Click to turn ON)")

        # Divider
        div1 = tk.Frame(self.container, bg=BORDER_COLOR, height=1 if is_v else 22, width=32 if is_v else 1)
        div1.pack(side=side_pack, padx=3, pady=3)

        # 4. Brightness Section
        btn_bup = make_icon_btn(self.container, "🔆", lambda: self.step_dimming(10), font=("Segoe UI Emoji", 10), fg=ACCENT_GOLD)
        btn_bup.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_bup, "Increase Brightness (+10%)")

        dim_val = self.bulb_state.get("dimming", 85)
        self.lbl_dim = tk.Label(self.container, text=f"{dim_val}%", font=(FONT_MAIN, 7, "bold"),
                                fg=TEXT_WHITE, bg=BG_CARD, padx=2, pady=1, cursor="hand2")
        self.lbl_dim.pack(side=side_pack, padx=2, pady=1)
        self.lbl_dim.bind("<Button-1>", lambda e: self.cycle_dimming())
        ToolTip(self.lbl_dim, lambda: f"Brightness: {self.bulb_state.get('dimming', 85)}%\n(Click to cycle 25% → 50% → 75% → 100%)")

        btn_bdn = make_icon_btn(self.container, "🔅", lambda: self.step_dimming(-10), font=("Segoe UI Emoji", 10), fg=TEXT_MUTED)
        btn_bdn.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_bdn, "Decrease Brightness (-10%)")

        # Divider
        div2 = tk.Frame(self.container, bg=BORDER_COLOR, height=1 if is_v else 22, width=32 if is_v else 1)
        div2.pack(side=side_pack, padx=3, pady=3)

        # 5. CCT Color Temperature Pill
        temp_val = self.bulb_state.get("temp", 6500)
        cct_color = kelvin_to_rgb_hex(temp_val)
        self.cct_pill = tk.Label(self.container, text=" " if is_v else "  ", font=(FONT_MAIN, 4),
                                 bg=cct_color, padx=3, pady=2, cursor="hand2")
        self.cct_pill.pack(side=side_pack, padx=2, pady=2)
        ToolTip(self.cct_pill, lambda: f"Color Temperature: {self.bulb_state.get('temp', 6500)}K\n({self._get_temp_desc()})")

        # 6. Presets (Icons Only)
        presets = [
            ("☀️", 6500, 100, "Daylight (6500K, 100%)"),
            ("❄️", 6500, 100, "Cool Blue (6500K, 100%)"),
            ("📖", 5000, 100, "Study / Focus (5000K, 100%)"),
            ("☕", 3500, 80, "Warm White (3500K, 80%)"),
            ("🕯️", 3000, 30, "Candlelight (3000K, 30%)"),
            ("🌙", 3000, 10, "Night Light (3000K, 10%)")
        ]

        for icon, temp, dim, desc in presets:
            p_btn = make_icon_btn(self.container, icon, lambda t=temp, d=dim: self.apply_preset(t, d), font=("Segoe UI Emoji", 10))
            p_btn.pack(side=side_pack, padx=2, pady=1)
            ToolTip(p_btn, desc)

        # Divider
        div3 = tk.Frame(self.container, bg=BORDER_COLOR, height=1 if is_v else 22, width=32 if is_v else 1)
        div3.pack(side=side_pack, padx=3, pady=3)

        # 7. Utilities & Window Controls
        # Minimize to Tray Button (Replaces Snap to Mining Sentry!)
        btn_min = make_icon_btn(self.container, "📥", self.minimize_to_tray, font=("Segoe UI Emoji", 9), fg=ACCENT_CYAN)
        btn_min.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_min, "Minimise to Top Tray (Keep running in background)")

        # Orientation Toggle
        btn_rot = make_icon_btn(self.container, "⇄", self.toggle_orientation, font=(FONT_MAIN, 9, "bold"), fg=ACCENT_CYAN)
        btn_rot.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_rot, f"Switch to {'Horizontal' if is_v else 'Vertical'} Strip Remote")

        # Schedules & Automation
        btn_sch = make_icon_btn(self.container, "⏰", self.open_schedules, font=(FONT_EMOJI, 9), fg=ACCENT_GOLD)
        btn_sch.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_sch, "Schedules & Automation (Auto Turn ON/OFF & Presets)")

        # Settings
        btn_set = make_icon_btn(self.container, "⚙️", self.open_settings, font=(FONT_EMOJI, 9), fg=TEXT_MUTED)
        btn_set.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_set, "Bulb Settings (IP & Security Key)")

        # Pin (Always on Top)
        is_pinned = self.config.get("always_on_top", True)
        self.btn_pin = make_icon_btn(self.container, "📌", self.toggle_pin, font=("Segoe UI Emoji", 9),
                                     fg=ACCENT_GOLD if is_pinned else TEXT_MUTED)
        self.btn_pin.pack(side=side_pack, padx=2, pady=1)
        ToolTip(self.btn_pin, lambda: "Always on Top: ON" if self.config.get("always_on_top", True) else "Always on Top: OFF")

        # Hide to Tray (X button)
        btn_cls = make_icon_btn(self.container, "✕", self.minimize_to_tray, font=(FONT_MAIN, 9, "bold"),
                                fg=TEXT_MUTED, active_bg=ACCENT_RED)
        btn_cls.pack(side=side_pack, padx=2, pady=1)
        ToolTip(btn_cls, "Hide to Top Tray (Right-click tray icon to Quit)")

    def toggle_remote_visibility(self):
        if self.is_minimized:
            self.show_from_tray()
        else:
            self.minimize_to_tray()

    def minimize_to_tray(self):
        self.withdraw()
        self.is_minimized = True
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.update_menu()

    def show_from_tray(self):
        self.deiconify()
        self.lift()
        self.wm_attributes("-topmost", self.config.get("always_on_top", True))
        self.is_minimized = False
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.update_menu()

    def _get_status_tooltip(self) -> str:
        online = self.bulb_state.get("online", False)
        if online:
            rssi = self.bulb_state.get("rssi", 0)
            ip = getattr(self.controller, "ip", self.config.get("ip", "192.168.0.100"))
            return f"WiZ T-Bulb: Online (Grid OK)\nSignal: {rssi} dBm\nIP: {ip}"
        else:
            return "WiZ T-Bulb: Offline\n(Bulb unreachable or Mains Power Out)"

    def _get_temp_desc(self) -> str:
        t = self.bulb_state.get("temp", 6500)
        if t < 3500:
            return "Candlelight"
        elif t < 4500:
            return "Warm White"
        elif t < 5500:
            return "Neutral White"
        elif t < 6200:
            return "Daylight"
        else:
            return "Cool Blue"

    def _update_ui_state(self, state_data: Dict[str, Any]):
        disc_ip = state_data.get("discovered_ip")
        if disc_ip and disc_ip != self.config.get("ip"):
            self.config["ip"] = disc_ip
            save_config(self.config)

        self.bulb_state = dict(state_data)
        online = state_data.get("online", False)

        # Update Tray Icon and Title
        if hasattr(self, "tray_icon") and self.tray_icon:
            if not online:
                self.tray_icon.icon = self.tray_icons["offline"]
                self.tray_icon.title = "WiZ Bulb: Offline"
            elif state_data.get("state", False):
                self.tray_icon.icon = self.tray_icons["on"]
                self.tray_icon.title = f"WiZ Bulb: ON ({state_data.get('dimming', 85)}%)"
            else:
                self.tray_icon.icon = self.tray_icons["off"]
                self.tray_icon.title = "WiZ Bulb: OFF"

        if not online:
            if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
                self.lbl_status.config(fg=ACCENT_RED)
            if hasattr(self, "btn_power") and self.btn_power.winfo_exists():
                self.btn_power.config(text="⏻", bg=BG_CARD, fg=TEXT_MUTED)
            return

        is_on = state_data.get("state", False)
        dim = state_data.get("dimming", 85)
        temp = state_data.get("temp", 6500)

        if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
            self.lbl_status.config(fg=ACCENT_GREEN)

        if hasattr(self, "btn_power") and self.btn_power.winfo_exists():
            if is_on:
                self.btn_power.config(text="💡", bg=ACCENT_GOLD, fg="#121316")
            else:
                self.btn_power.config(text="⏻", bg=BG_CARD, fg=TEXT_MUTED)

        if hasattr(self, "lbl_dim") and self.lbl_dim.winfo_exists():
            self.lbl_dim.config(text=f"{dim}%")
        if hasattr(self, "cct_pill") and self.cct_pill.winfo_exists():
            self.cct_pill.config(bg=kelvin_to_rgb_hex(temp))

    def _start_background_polling(self):
        def poller():
            while self.polling_active:
                state_data = self.controller.get_state()
                self.after(0, lambda d=state_data: self._update_ui_state(d))
                time.sleep(self.config.get("poll_interval", 3.0))

        t = threading.Thread(target=poller, daemon=True)
        t.start()

    def refresh_state_async(self):
        def worker():
            state_data = self.controller.get_state()
            self.after(0, lambda d=state_data: self._update_ui_state(d))
        threading.Thread(target=worker, daemon=True).start()

    def set_power(self, state: bool):
        self.bulb_state["state"] = state
        if hasattr(self, "btn_power") and self.btn_power.winfo_exists():
            if state:
                self.btn_power.config(text="💡", bg=ACCENT_GOLD, fg="#121316")
            else:
                self.btn_power.config(text="⏻", bg=BG_CARD, fg=TEXT_MUTED)
        self._send_command_async(state=state)

    def toggle_power(self):
        current_state = bool(self.bulb_state.get("state", False))
        self.set_power(not current_state)

    def set_dimming(self, dim: int):
        d = max(10, min(100, int(dim)))
        self.bulb_state["dimming"] = d
        if hasattr(self, "lbl_dim") and self.lbl_dim.winfo_exists():
            self.lbl_dim.config(text=f"{d}%")
        self._send_command_async(dimming=d)

    def step_dimming(self, delta: int):
        cur = self.bulb_state.get("dimming", 85)
        self.set_dimming(cur + delta)

    def cycle_dimming(self):
        steps = [25, 50, 75, 100, 10]
        cur = self.bulb_state.get("dimming", 85)
        next_step = steps[0]
        for s in steps:
            if s > cur:
                next_step = s
                break
        self.set_dimming(next_step)

    def apply_preset(self, temp: int, dim: int):
        self.bulb_state["state"] = True
        self.bulb_state["temp"] = temp
        self.bulb_state["dimming"] = dim
        if hasattr(self, "btn_power") and self.btn_power.winfo_exists():
            self.btn_power.config(text="💡", bg=ACCENT_GOLD, fg="#121316")
        if hasattr(self, "lbl_dim") and self.lbl_dim.winfo_exists():
            self.lbl_dim.config(text=f"{dim}%")
        if hasattr(self, "cct_pill") and self.cct_pill.winfo_exists():
            self.cct_pill.config(bg=kelvin_to_rgb_hex(temp))
        self._send_command_async(state=True, temp=temp, dimming=dim)

    def _send_command_async(self, **kwargs):
        def worker():
            success, msg = self.controller.set_pilot(**kwargs)
            if not success:
                print(f"Command error: {msg}", file=sys.stderr)
            self.refresh_state_async()

        threading.Thread(target=worker, daemon=True).start()

    def toggle_orientation(self):
        self.orientation = "horizontal" if self.orientation == "vertical" else "vertical"
        self.config["orientation"] = self.orientation
        self.config["win_x"] = -1
        self.config["win_y"] = -1
        save_config(self.config)
        self._build_ui()
        self._apply_geometry()

    def toggle_pin(self):
        new_val = not self.config.get("always_on_top", True)
        self.config["always_on_top"] = new_val
        self.wm_attributes("-topmost", new_val)
        if hasattr(self, "btn_pin") and self.btn_pin.winfo_exists():
            self.btn_pin.config(fg=ACCENT_GOLD if new_val else TEXT_MUTED)
        save_config(self.config)

    def open_settings(self):
        if self.settings_dialog and self.settings_dialog.winfo_exists():
            self.settings_dialog.lift()
            return
        self.settings_dialog = SettingsDialog(self, self.config, self._on_settings_saved)

    def _on_settings_saved(self, new_ip: str, new_key: str):
        self.config["ip"] = new_ip
        self.config["signing_key"] = new_key
        save_config(self.config)
        self.controller = WizBulbController(ip=new_ip, signing_key=new_key)
        self.refresh_state_async()

    def open_schedules(self):
        if self.schedule_dialog and self.schedule_dialog.winfo_exists():
            self.schedule_dialog.lift()
            return
        self.schedule_dialog = ScheduleDialog(self, self.config, self._on_schedules_updated)

    def _on_schedules_updated(self, new_schedules: list):
        self.config["schedules"] = new_schedules
        save_config(self.config)

    def _start_scheduler(self):
        self._executed_triggers = set()

        def check_schedules():
            if not getattr(self, "polling_active", True):
                return
            now = time.localtime()
            current_hm = f"{now.tm_hour:02d}:{now.tm_min:02d}"
            current_day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.tm_wday]
            is_weekend = now.tm_wday in [5, 6]
            is_weekday = now.tm_wday in [0, 1, 2, 3, 4]
            date_prefix = f"{now.tm_year}-{now.tm_yday}"

            schedules = self.config.get("schedules", [])
            for sch in schedules:
                if not sch.get("enabled", True):
                    continue
                if sch.get("time") != current_hm:
                    continue

                repeat = sch.get("repeat", "Everyday")
                if repeat == "Weekdays (Mon-Fri)" and not is_weekday:
                    continue
                if repeat == "Weekends (Sat-Sun)" and not is_weekend:
                    continue
                if isinstance(repeat, list) and current_day not in repeat:
                    continue

                trigger_id = sch.get("id", f"{sch.get('time')}_{sch.get('action')}")
                trigger_key = f"{date_prefix}:{trigger_id}"
                if trigger_key in self._executed_triggers:
                    continue

                # Execute action
                self._executed_triggers.add(trigger_key)
                action = sch.get("action", "")
                if action == "turn_on":
                    self.set_power(True)
                elif action == "turn_off":
                    self.set_power(False)
                elif action == "preset":
                    temp = sch.get("temp", 6500)
                    dim = sch.get("dim", 100)
                    self.apply_preset(temp, dim)

            # Prune old trigger records
            if len(self._executed_triggers) > 200:
                self._executed_triggers = {k for k in self._executed_triggers if k.startswith(date_prefix)}

            self.after(5000, check_schedules)

        self.after(5000, check_schedules)

    def quit_app(self):
        self.polling_active = False
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = WizFloatingWidget()
    app.mainloop()
