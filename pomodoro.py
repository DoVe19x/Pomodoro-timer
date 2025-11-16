import time
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap import Style
from PIL import Image, ImageTk, ImageFilter, ImageOps
import vlc
import math

# ========================
# Paramètres Pomodoro
# ========================
SHORT_BREAK_TIME = 5 * 60
LONG_BREAK_TIME = 15 * 60

# ========================
# Fichiers
# ========================
LOFI_PATH = "lofi.mp3"
BELL_PATH = "clochette.mp3"
BG_IMAGE = "IMG.JPG"   # attention au nom exact


class PomodoroTimer:
    def __init__(self):
        # --- Fenêtre ---
        self.root = tk.Tk()
        self.root.title("Pomodoro • Cosy Focus")
        self.root.minsize(540, 440)

        # Thème & Couleurs
        self.style = Style(theme="minty")
        self.root.configure(bg=self.style.colors.bg)

        # --- États internes ---
        self.phase = "work"
        self.pomodoros_completed = 0
        self.is_running = False
        self.start_ts = None
        self.target_ts = None

        # Durée de travail (select 25 / 30 / 35)
        self.work_var = tk.IntVar(value=25)
        self.duration = self._get_current_work_duration()

        # --- VLC Audio ---
        try:
            self.vlc_instance = vlc.Instance("--no-video")
        except:
            messagebox.showerror("Erreur VLC", "libVLC introuvable. Installe VLC.")
            raise

        self.lofi_player = None
        self.bell_player = None

        # --- Fond d'écran ---
        self.bg_original = None
        self.bg_photo = None
        self.bg_label = tk.Label(self.root, bd=0)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.resize_job = None
        self.last_bg_size = (0, 0)
        self._load_background()

        # --- Carte principale (simple, centrée) ---
        self.card = ttk.Frame(self.root, padding=24, bootstyle="light")
        self.card.pack(expand=True, pady=20, padx=20)

        # --- HEADER ---
        header = ttk.Frame(self.card)
        header.pack(pady=(0, 8), fill="x")

        self.title_label = ttk.Label(
            header,
            text="Session de travail",
            font=("Segoe UI", 15, "bold")
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ttk.Label(
            header,
            text="Choisis ton rythme, mets du lofi, respire 🌿",
            font=("Segoe UI", 9)
        )
        self.subtitle_label.pack(anchor="w")

        # --- SÉLECTEUR DE DURÉE ---
        dur_frame = ttk.Frame(self.card)
        dur_frame.pack(pady=(8, 10))

        ttk.Label(dur_frame, text="Durée de focus", font=("Segoe UI", 9, "bold"))\
            .pack(side=tk.LEFT, padx=(0, 6))

        for mins in (25, 30, 35):
            rb = ttk.Radiobutton(
                dur_frame,
                text=f"{mins} min",
                variable=self.work_var,
                value=mins,
                command=self._on_work_duration_changed,
                bootstyle="success-toolbutton",
            )
            rb.pack(side=tk.LEFT, padx=2)

        # --- PROGRESS RING ---
        self.canvas_size = 260
        self.canvas = tk.Canvas(
            self.card,
            width=self.canvas_size,
            height=self.canvas_size,
            highlightthickness=0,
            bg=self.style.colors.light
        )
        self.canvas.pack(pady=5)

        # --- TIMER TEXTE ---
        self.timer_label = ttk.Label(
            self.card,
            text=self._format_time(self.duration),
            font=("Segoe UI", 36, "bold")
        )
        self.timer_label.pack(pady=(8, 16))

        # --- BOUTONS ---
        btns = ttk.Frame(self.card)
        btns.pack(pady=(0, 8))

        self.start_button = ttk.Button(
            btns, text="Start",
            command=self.start_timer,
            bootstyle="success-outline", width=10
        )
        self.start_button.grid(row=0, column=0, padx=6)

        self.stop_button = ttk.Button(
            btns, text="Stop",
            command=self.stop_timer,
            state=tk.DISABLED, width=10,
            bootstyle="danger"
        )
        self.stop_button.grid(row=0, column=1, padx=6)

        self.skip_button = ttk.Button(
            btns, text="Skip",
            command=self.skip_phase,
            state=tk.DISABLED, width=10,
            bootstyle="secondary-outline"
        )
        self.skip_button.grid(row=0, column=2, padx=6)

        # --- STATISTIQUES ---
        self.stats_label = ttk.Label(
            self.card,
            text="0 session complétée • Pense à t’hydrater 💧",
            font=("Segoe UI", 9)
        )
        self.stats_label.pack(pady=(6, 0))

        # Responsive uniquement pour le fond
        self.root.bind("<Configure>", self._on_root_resize)

        # Affichage init
        self._update_display(self.duration)
        self._draw_ring(0.0)

        self.root.mainloop()

    # =========================================================
    # UTILITAIRES
    # =========================================================
    def _get_current_work_duration(self):
        return int(self.work_var.get()) * 60

    def _format_time(self, seconds):
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _on_work_duration_changed(self):
        """Quand on change 25/30/35 min et que rien ne tourne."""
        if not self.is_running and self.phase == "work":
            self.duration = self._get_current_work_duration()
            self._update_display(self.duration)
            self._draw_ring(0.0)

    # =========================================================
    # AUDIO (VLC)
    # =========================================================
    def play_lofi(self, volume=22):
        try:
            if self.lofi_player is None:
                self.lofi_player = self.vlc_instance.media_player_new()
                media = self.vlc_instance.media_new(LOFI_PATH)
                media.add_option("input-repeat=-1")
                self.lofi_player.set_media(media)

            self.lofi_player.stop()
            self.lofi_player.audio_set_volume(volume)
            self.lofi_player.play()
        except Exception as e:
            print("⚠️ Lofi error:", e)

    def stop_lofi(self):
        if self.lofi_player:
            try:
                self.lofi_player.stop()
            except:
                pass

    def ring_bell(self, volume=85):
        try:
            bell = self.vlc_instance.media_player_new()
            media = self.vlc_instance.media_new(BELL_PATH)
            bell.set_media(media)
            bell.audio_set_volume(volume)
            bell.play()
            self.bell_player = bell
            self.root.after(4000, self._cleanup_bell)
        except:
            pass

    def _cleanup_bell(self):
        try:
            if self.bell_player and not self.bell_player.is_playing():
                self.bell_player.stop()
        except:
            pass
        self.bell_player = None

    # =========================================================
    # BACKGROUND
    # =========================================================
    def _load_background(self):
        try:
            img = Image.open(BG_IMAGE).convert("RGB")
            img = img.filter(ImageFilter.GaussianBlur(1.3))
            self.bg_original = img
            self._resize_background(True)
        except:
            self.root.configure(bg="#1a1f2b")

    def _on_root_resize(self, event):
        if event.widget is not self.root:
            return
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self._resize_background(False)
        self.resize_job = self.root.after(
            120, lambda: self._resize_background(True)
        )

    def _resize_background(self, sharp=True):
        if not self.bg_original:
            return

        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())

        bg = ImageOps.fit(
            self.bg_original,
            (w, h),
            method=Image.Resampling.LANCZOS
        )

        if not sharp:
            bg = bg.resize((w//2, h//2), Image.Resampling.BILINEAR)\
                   .resize((w, h), Image.Resampling.BILINEAR)

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 60))
        bg = bg.convert("RGBA")
        bg.alpha_composite(overlay)

        self.bg_photo = ImageTk.PhotoImage(bg)
        self.bg_label.config(image=self.bg_photo)
        self.last_bg_size = (w, h)

    # =========================================================
    # LOGIQUE POMODORO
    # =========================================================
    def start_timer(self):
        if self.is_running:
            return

        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.skip_button.config(state=tk.NORMAL)

        if self.phase == "work":
            self.duration = self._get_current_work_duration()
            self.title_label.config(text="Session de travail")
            self.play_lofi()
        else:
            self.title_label.config(text="Pause")
            self.stop_lofi()

        now = time.monotonic()
        self.start_ts = now
        self.target_ts = now + self.duration

        self._tick()

    def stop_timer(self):
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.skip_button.config(state=tk.DISABLED)
        self.stop_lofi()

    def skip_phase(self):
        if self.is_running:
            self.target_ts = time.monotonic()

    def _end_work(self):
        self.stop_lofi()
        self.ring_bell()
        self.pomodoros_completed += 1
        self._update_stats()

        long_break = (self.pomodoros_completed % 4 == 0)
        self.phase = "break"
        self.duration = LONG_BREAK_TIME if long_break else SHORT_BREAK_TIME

        msg = "Longue pause, respire 15 min 🌙" if long_break else \
              "Petite pause 5 min, bouge un peu 🧘"
        messagebox.showinfo("Pause", msg)

        self._restart_phase()

    def _end_break(self):
        self.ring_bell()
        self.phase = "work"
        self.duration = self._get_current_work_duration()

        messagebox.showinfo(
            "Travail",
            f"C’est reparti pour {self.work_var.get()} min de focus 💡"
        )
        self._restart_phase()

    def _restart_phase(self):
        now = time.monotonic()
        self.start_ts = now
        self.target_ts = now + self.duration

        if self.phase == "work":
            self.play_lofi()
        else:
            self.stop_lofi()

    def _tick(self):
        if not self.is_running:
            return

        now = time.monotonic()
        remaining = max(0, self.target_ts - now)
        progress = 1 - remaining / self.duration if self.duration > 0 else 1.0

        self._update_display(remaining)
        self._draw_ring(progress)

        if remaining <= 0:
            if self.phase == "work":
                self._end_work()
            else:
                self._end_break()

        self.root.after(100, self._tick)

    # =========================================================
    # AFFICHAGE
    # =========================================================
    def _update_display(self, remaining):
        self.timer_label.config(text=self._format_time(remaining))

    def _draw_ring(self, progress):
        self.canvas.delete("all")

        pad = 16
        cx = cy = self.canvas_size // 2
        r = (self.canvas_size - 2 * pad) // 2

        x0, y0 = pad, pad
        x1, y1 = self.canvas_size - pad, self.canvas_size - pad

        # cercle gris
        self.canvas.create_oval(x0, y0, x1, y1, outline="#E6EAF2", width=14)

        # arc progressif
        angle = max(0.0, min(1.0, progress)) * 360.0
        accent = "#2DB47C" if self.phase == "work" else "#5B8DEF"

        self.canvas.create_arc(
            x0, y0, x1, y1,
            start=-90,
            extent=angle,
            style="arc",
            outline=accent,
            width=14
        )

        # petit point
        angle_rad = math.radians(-90 + angle)
        px = cx + r * math.cos(angle_rad)
        py = cy + r * math.sin(angle_rad)
        self.canvas.create_oval(px-5, py-5, px+5, py+5, fill=accent, outline="")

    # =========================================================
    # STATISTIQUES
    # =========================================================
    def _update_stats(self):
        n = self.pomodoros_completed
        if n == 0:
            txt = "0 session complétée • Pense à t’hydrater 💧"
        elif n == 1:
            txt = "1 session complétée • Beau début 🌱"
        else:
            txt = f"{n} sessions complétées • Continue comme ça 🔥"
        self.stats_label.config(text=txt)


if __name__ == "__main__":
    PomodoroTimer()
