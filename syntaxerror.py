import asyncio
import io
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    Image = None
    ImageOps = None
    ImageTk = None

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winsdk.windows.storage.streams import DataReader

    WINDOWS_MEDIA_AVAILABLE = True
except ImportError:
    MediaManager = None
    DataReader = None
    WINDOWS_MEDIA_AVAILABLE = False


DARK_THEME = {
    "window_bg": "#101318",
    "panel_bg": "#1A1F2B",
    "card_bg": "#262D3A",
    "display_bg": "#242B3D",
    "text_main": "#F2F5FF",
    "text_secondary": "#AEB9CF",
    "text_muted": "#8FA2C8",
    "button_num": "#2B3348",
    "button_num_active": "#36405A",
    "button_fn": "#303956",
    "button_fn_active": "#3A4566",
    "button_accent": "#4F7CFF",
    "button_accent_active": "#6A93FF",
    "progress_trough": "#2A3142",
    "progress_bar": "#4F7CFF",
}

LIGHT_THEME = {
    "window_bg": "#EEF2F7",
    "panel_bg": "#FFFFFF",
    "card_bg": "#E9EEF7",
    "display_bg": "#F4F7FC",
    "text_main": "#182033",
    "text_secondary": "#3C4C6B",
    "text_muted": "#5A6F93",
    "button_num": "#DFE6F3",
    "button_num_active": "#CCD7EA",
    "button_fn": "#D3DDF0",
    "button_fn_active": "#C2D0E8",
    "button_accent": "#3C72F7",
    "button_accent_active": "#5B88FB",
    "progress_trough": "#D9E2F2",
    "progress_bar": "#3C72F7",
}


@dataclass
class MediaState:
    title: str
    artist: str
    album: str
    duration_ms: int
    position_ms: int
    is_playing: bool
    cover_bytes: bytes | None


class CalculatorPanel:
    def __init__(self, parent: tk.Widget, theme: dict):
        self.parent = parent
        self.expression = ""
        self.display_var = tk.StringVar(value="0")
        self.theme = theme
        self.button_specs = []
        self._build_ui(parent)

    def _build_ui(self, parent: tk.Widget):
        self.container = tk.Frame(parent)
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        self.display = tk.Entry(
            self.container,
            textvariable=self.display_var,
            justify="right",
            font=("Segoe UI Semibold", 30),
            bd=0,
            state="readonly",
            disabledforeground=self.theme["text_main"],
        )
        self.display.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=12, pady=(12, 14), ipady=12)

        buttons = [
            ("C", 1, 0), ("<-", 1, 1), ("/", 1, 2), ("*", 1, 3),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2), ("-", 2, 3),
            ("4", 3, 0), ("5", 3, 1), ("6", 3, 2), ("+", 3, 3),
            ("1", 4, 0), ("2", 4, 1), ("3", 4, 2), ("=", 4, 3),
            ("0", 5, 0), (".", 5, 1), ("00", 5, 2),
        ]

        for col in range(4):
            self.container.grid_columnconfigure(col, weight=1)
        for row in range(1, 6):
            self.container.grid_rowconfigure(row, weight=1)

        for text, row, col in buttons:
            role = "num"
            if text in {"C", "<-"}:
                role = "fn"
            if text in {"/", "*", "-", "+", "="}:
                role = "accent"

            btn = tk.Button(
                self.container,
                text=text,
                command=lambda t=text: self._on_button(t),
                font=("Segoe UI Semibold", 14),
                bd=0,
                relief="flat",
                highlightthickness=0,
                padx=10,
                pady=10,
            )
            btn.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            self.button_specs.append((btn, role))

        root = parent.winfo_toplevel()
        root.bind("<Return>", lambda _: self._on_button("="))
        root.bind("<BackSpace>", lambda _: self._on_button("<-"))
        root.bind("<Escape>", lambda _: self._on_button("C"))

        self.apply_theme(self.theme)

    def apply_theme(self, theme: dict):
        self.theme = theme
        self.container.configure(bg=theme["panel_bg"])
        self.display.configure(
            readonlybackground=theme["display_bg"],
            fg=theme["text_main"],
            disabledforeground=theme["text_main"],
        )

        for btn, role in self.button_specs:
            if role == "fn":
                bg = theme["button_fn"]
                active_bg = theme["button_fn_active"]
            elif role == "accent":
                bg = theme["button_accent"]
                active_bg = theme["button_accent_active"]
            else:
                bg = theme["button_num"]
                active_bg = theme["button_num_active"]

            btn.configure(
                bg=bg,
                fg=("white" if role == "accent" else theme["text_main"]),
                activebackground=active_bg,
                activeforeground=("white" if role == "accent" else theme["text_main"]),
            )

    def _on_button(self, value: str):
        if value == "C":
            self.expression = ""
            self.display_var.set("0")
            return
        if value == "<-":
            self.expression = self.expression[:-1]
            self.display_var.set(self.expression if self.expression else "0")
            return
        if value == "=":
            self._calculate()
            return

        self.expression += value
        self.display_var.set(self.expression)

    def _calculate(self):
        if not self.expression:
            return
        try:
            result = str(eval(self.expression, {"__builtins__": {}}, {}))
            self.expression = result
            self.display_var.set(result)
        except Exception:
            self.expression = ""
            self.display_var.set("Error")


class WindowsMediaPanel:
    def __init__(self, parent: tk.Widget, theme: dict, style: ttk.Style):
        self.root = parent.winfo_toplevel()
        self.parent = parent
        self.theme = theme
        self.style = style

        self.poll_inflight = False
        self.duration_ms = 0
        self.position_ms = 0
        self.is_playing = False
        self.last_tick = time.monotonic()

        self.title_var = tk.StringVar(value="No media")
        self.artist_var = tk.StringVar(value="Artist: -")
        self.album_var = tk.StringVar(value="Album: -")
        self.time_var = tk.StringVar(value="00:00 / 00:00")
        self.status_var = tk.StringVar(value="Waiting for Windows media session...")

        self._build_ui(parent)
        self.root.after(400, self._ui_tick)
        self.root.after(1000, self._poll_once)

    def _build_ui(self, parent: tk.Widget):
        self.container = tk.Frame(parent)
        self.container.pack(fill="both", expand=True, padx=16, pady=16)

        self.cover_label = tk.Label(
            self.container,
            text="No Cover",
            font=("Segoe UI Semibold", 13),
            width=30,
            height=12,
        )
        self.cover_label.pack(fill="x", padx=14, pady=(14, 12))

        self.title_label = tk.Label(
            self.container,
            textvariable=self.title_var,
            font=("Segoe UI Semibold", 16),
            wraplength=390,
            justify="center",
        )
        self.title_label.pack(padx=10, pady=(0, 6))

        self.artist_label = tk.Label(
            self.container,
            textvariable=self.artist_var,
            font=("Segoe UI", 11),
            wraplength=390,
            justify="center",
        )
        self.artist_label.pack(padx=10, pady=(0, 4))

        self.album_label = tk.Label(
            self.container,
            textvariable=self.album_var,
            font=("Segoe UI", 10),
            wraplength=390,
            justify="center",
        )
        self.album_label.pack(padx=10, pady=(0, 10))

        self.progress = ttk.Progressbar(
            self.container,
            style="Media.Horizontal.TProgressbar",
            orient="horizontal",
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.pack(fill="x", padx=20, pady=(2, 8))

        self.time_label = tk.Label(self.container, textvariable=self.time_var, font=("Consolas", 11))
        self.time_label.pack(pady=(0, 8))

        self.controls = tk.Frame(self.container)
        self.controls.pack(pady=(4, 10))

        self.prev_btn = tk.Button(
            self.controls,
            text="<<",
            command=self._previous,
            font=("Segoe UI Semibold", 13),
            bd=0,
            width=5,
            padx=10,
            pady=8,
        )
        self.prev_btn.grid(row=0, column=0, padx=6)

        self.play_btn = tk.Button(
            self.controls,
            text=">/||",
            command=self._toggle_play_pause,
            font=("Segoe UI Semibold", 13),
            bd=0,
            width=7,
            padx=10,
            pady=8,
        )
        self.play_btn.grid(row=0, column=1, padx=6)

        self.next_btn = tk.Button(
            self.controls,
            text=">>",
            command=self._next,
            font=("Segoe UI Semibold", 13),
            bd=0,
            width=5,
            padx=10,
            pady=8,
        )
        self.next_btn.grid(row=0, column=2, padx=6)

        self.status_label = tk.Label(
            self.container,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            wraplength=390,
            justify="center",
        )
        self.status_label.pack(padx=12, pady=(2, 14))

        self.apply_theme(self.theme)

    def apply_theme(self, theme: dict):
        self.theme = theme
        self.container.configure(bg=theme["panel_bg"])
        self.cover_label.configure(bg=theme["card_bg"], fg=theme["text_main"])
        self.title_label.configure(bg=theme["panel_bg"], fg=theme["text_main"])
        self.artist_label.configure(bg=theme["panel_bg"], fg=theme["text_secondary"])
        self.album_label.configure(bg=theme["panel_bg"], fg=theme["text_muted"])
        self.time_label.configure(bg=theme["panel_bg"], fg=theme["text_main"])
        self.controls.configure(bg=theme["panel_bg"])
        self.status_label.configure(bg=theme["panel_bg"], fg=theme["text_muted"])

        self.prev_btn.configure(
            bg=theme["button_fn"],
            fg=theme["text_main"],
            activebackground=theme["button_fn_active"],
            activeforeground=theme["text_main"],
        )
        self.next_btn.configure(
            bg=theme["button_fn"],
            fg=theme["text_main"],
            activebackground=theme["button_fn_active"],
            activeforeground=theme["text_main"],
        )
        self.play_btn.configure(
            bg=theme["button_accent"],
            fg="white",
            activebackground=theme["button_accent_active"],
            activeforeground="white",
        )

        self.style.configure(
            "Media.Horizontal.TProgressbar",
            troughcolor=theme["progress_trough"],
            background=theme["progress_bar"],
            bordercolor=theme["progress_trough"],
            lightcolor=theme["progress_bar"],
            darkcolor=theme["progress_bar"],
        )

    def _poll_once(self):
        if self.poll_inflight:
            self.root.after(1500, self._poll_once)
            return

        self.poll_inflight = True

        def worker():
            try:
                state = asyncio.run(self._read_windows_media())
                self.root.after(0, lambda: self._apply_state(state))
            except Exception as exc:
                self.root.after(0, lambda: self.status_var.set(f"Media error: {exc}"))
            finally:
                self.root.after(0, self._poll_done)

        threading.Thread(target=worker, daemon=True).start()

    def _poll_done(self):
        self.poll_inflight = False
        self.root.after(1500, self._poll_once)

    async def _read_windows_media(self) -> MediaState | None:
        if not WINDOWS_MEDIA_AVAILABLE:
            return None

        manager = await MediaManager.request_async()
        session = manager.get_current_session()
        if session is None:
            return None

        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        playback_info = session.get_playback_info()

        duration_ms = int(max(0.0, timeline.end_time.total_seconds()) * 1000)
        position_ms = int(max(0.0, timeline.position.total_seconds()) * 1000)

        status = playback_info.playback_status
        is_playing = str(status).lower().endswith("playing")

        title = props.title or "Unknown title"
        artist = props.artist or "Unknown artist"
        album = props.album_title or "-"
        cover_bytes = await self._read_thumbnail(props.thumbnail)

        return MediaState(
            title=title,
            artist=artist,
            album=album,
            duration_ms=duration_ms,
            position_ms=position_ms,
            is_playing=is_playing,
            cover_bytes=cover_bytes,
        )

    async def _read_thumbnail(self, thumbnail_ref) -> bytes | None:
        if thumbnail_ref is None or DataReader is None:
            return None

        try:
            stream = await thumbnail_ref.open_read_async()
            size = int(stream.size)
            if size <= 0:
                return None

            reader = DataReader(stream)
            await reader.load_async(size)
            data = bytearray(size)
            reader.read_bytes(data)
            reader.close()
            return bytes(data)
        except Exception:
            return None

    def _apply_state(self, state: MediaState | None):
        if not WINDOWS_MEDIA_AVAILABLE:
            self.status_var.set("Install winsdk: pip install winsdk")
            self.title_var.set("Windows media API unavailable")
            return

        if state is None:
            self.title_var.set("Nothing playing now")
            self.artist_var.set("Artist: -")
            self.album_var.set("Album: -")
            self.duration_ms = 0
            self.position_ms = 0
            self.is_playing = False
            self._set_cover(None)
            self.status_var.set("No active media session in Windows")
            self._refresh_time()
            return

        self.title_var.set(state.title)
        self.artist_var.set(f"Artist: {state.artist}")
        self.album_var.set(f"Album: {state.album}")
        self.duration_ms = state.duration_ms
        self.position_ms = state.position_ms
        self.is_playing = state.is_playing
        self.status_var.set("Playing" if state.is_playing else "Paused")
        self._set_cover(state.cover_bytes)
        self._refresh_time()

    def _set_cover(self, data: bytes | None):
        if data is None or Image is None or ImageOps is None or ImageTk is None:
            self.cover_label.configure(image="", text="No Cover")
            self.cover_label.image = None
            return

        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            resample_enum = getattr(Image, "Resampling", Image)
            image = ImageOps.fit(image, (390, 280), method=resample_enum.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.cover_label.configure(image=photo, text="")
            self.cover_label.image = photo
        except Exception:
            self.cover_label.configure(image="", text="No Cover")
            self.cover_label.image = None

    def _ui_tick(self):
        now = time.monotonic()
        delta_ms = int((now - self.last_tick) * 1000)
        self.last_tick = now

        if self.is_playing and self.duration_ms > 0:
            self.position_ms = min(self.duration_ms, self.position_ms + max(0, delta_ms))

        self._refresh_time()
        self.root.after(400, self._ui_tick)

    def _refresh_time(self):
        self.time_var.set(f"{self._fmt(self.position_ms)} / {self._fmt(self.duration_ms)}")
        if self.duration_ms > 0:
            value = max(0.0, min(100.0, (self.position_ms / self.duration_ms) * 100.0))
            self.progress.configure(value=value)
        else:
            self.progress.configure(value=0)

    async def _do_control(self, action: str):
        manager = await MediaManager.request_async()
        session = manager.get_current_session()
        if session is None:
            return

        if action == "toggle":
            await session.try_toggle_play_pause_async()
        elif action == "next":
            await session.try_skip_next_async()
        elif action == "previous":
            await session.try_skip_previous_async()

    def _run_control(self, action: str):
        if not WINDOWS_MEDIA_AVAILABLE:
            messagebox.showerror("Missing dependency", "Install winsdk: pip install winsdk")
            return

        def worker():
            try:
                asyncio.run(self._do_control(action))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_play_pause(self):
        self._run_control("toggle")

    def _next(self):
        self._run_control("next")

    def _previous(self):
        self._run_control("previous")

    @staticmethod
    def _fmt(milliseconds: int) -> str:
        total_seconds = max(0, int(milliseconds / 1000))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"


class SuperApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.theme_name = "dark"
        self.theme = DARK_THEME

        root.title("Calculator + Windows Media")
        root.geometry("500x760")
        root.minsize(480, 720)

        self.style = ttk.Style(root)
        self.style.theme_use("default")

        self.topbar = tk.Frame(root)
        self.topbar.pack(fill="x", padx=12, pady=(10, 6))

        self.title_label = tk.Label(self.topbar, text="Utilities")
        self.title_label.pack(side="left")

        self.theme_btn = tk.Button(self.topbar, command=self.toggle_theme, padx=10, pady=6, bd=0)
        self.theme_btn.pack(side="right")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.calc_tab = tk.Frame(self.notebook)
        self.media_tab = tk.Frame(self.notebook)
        self.notebook.add(self.calc_tab, text="Calculator")
        self.notebook.add(self.media_tab, text="Windows Media")

        self.calculator_panel = CalculatorPanel(self.calc_tab, self.theme)
        self.media_panel = WindowsMediaPanel(self.media_tab, self.theme, self.style)

        self.apply_theme()

    def toggle_theme(self):
        if self.theme_name == "dark":
            self.theme_name = "light"
            self.theme = LIGHT_THEME
        else:
            self.theme_name = "dark"
            self.theme = DARK_THEME
        self.apply_theme()

    def apply_theme(self):
        theme = self.theme

        self.root.configure(bg=theme["window_bg"])
        self.topbar.configure(bg=theme["window_bg"])
        self.title_label.configure(bg=theme["window_bg"], fg=theme["text_secondary"], font=("Segoe UI Semibold", 11))

        self.theme_btn.configure(
            text=("Light Theme" if self.theme_name == "dark" else "Dark Theme"),
            bg=theme["button_fn"],
            fg=theme["text_main"],
            activebackground=theme["button_fn_active"],
            activeforeground=theme["text_main"],
            font=("Segoe UI Semibold", 10),
        )

        self.calc_tab.configure(bg=theme["panel_bg"])
        self.media_tab.configure(bg=theme["panel_bg"])

        self.style.configure("TNotebook", background=theme["window_bg"], borderwidth=0)
        self.style.configure(
            "TNotebook.Tab",
            background=theme["card_bg"],
            foreground=theme["text_secondary"],
            padding=[12, 6],
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", theme["panel_bg"])],
            foreground=[("selected", theme["text_main"])],
        )

        self.calculator_panel.apply_theme(theme)
        self.media_panel.apply_theme(theme)


def main():
    root = tk.Tk()
    SuperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
