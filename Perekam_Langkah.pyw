"""
PEREKAM LANGKAH untuk Sitata Bot
================================
Merekam: kombinasi shortcut, teks yang diketik, klik mouse (lokasi), scroll
(total panjang, presisi penuh) dan (opsional) perpindahan jendela.
Pergerakan mouse TIDAK direkam.
Hasilnya berupa kode siap tempel ke dalam daftar BUTTONS pada bot.

Persiapan (sekali saja, di Command Prompt):
    pip install -U pynput

Cara pakai:
    1. Jalankan file ini (klik ganda).
    2. Tekan F9 (atau tombol Mulai) -> perekaman dimulai.
    3. Kerjakan langkah Anda seperti biasa di Edge / AutoCAD / dll.
    4. Tekan F9 lagi -> berhenti. Salin hasilnya ke BUTTONS di bot.

Scroll halus (seperti touchpad 2 jari), hanya saat merekam:
    F7 = geser ke atas, F8 = geser ke bawah, sebesar "langkah" yang diatur
    di jendela perekam (mis. 0.1 = sepersepuluh geseran roda). Tahan tombol
    untuk bergeser terus-menerus. Geseran ikut terekam sebagai scroll(...).
    Tombol F7/F8 tidak diteruskan ke aplikasi selama merekam.

Jika aplikasi target berjalan sebagai Administrator, jalankan perekam ini
sebagai Administrator juga (Windows memblokir hook dari proses biasa).
"""
import sys
import json
import time
import ctypes
import threading
import queue
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, filedialog

if sys.platform != "win32":
    raise SystemExit("Perekam ini hanya untuk Windows.")

# Samakan skala koordinat dengan pyautogui (yang dipakai bot)
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

try:
    from pynput import keyboard, mouse
except ImportError:
    from tkinter import messagebox
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror(
        "Modul belum terpasang",
        "Buka Command Prompt lalu jalankan:\n\npip install pynput",
    )
    raise SystemExit

# ====== KONFIGURASI ======
APP_TITLE = "Perekam Langkah"
HOTKEY = keyboard.Key.f9          # tombol mulai/berhenti (tidak ikut direkam)
RECORD_FOCUS = True               # catat perpindahan jendela sebagai focus(...)
# Jika judul jendela mengandung salah satu kata ini, yang ditulis hanya kata
# tersebut (sama seperti gaya focus("Edge") di bot). Tambahkan sesuai kebutuhan.
FOCUS_KEYWORDS = ["Find and Replace", "Tataletak - Kementerian", "Edge", "AutoCAD"]
# Scroll: geseran beruntun digabung jadi SATU langkah scroll(total, x, y).
SCROLL_GAP = 1.0          # detik; jeda lebih lama dari ini = langkah scroll baru
SCROLL_POS_TOL = 40       # px; pointer bergeser lebih jauh = langkah scroll baru
RECORD_SCROLL_POS = True  # sertakan posisi pointer (x, y) pada scroll
# Scroll halus: tombol F-key (jangan pakai Ctrl/Shift, nanti dianggap zoom/horizontal)
FINE_UP_KEY = "f7"
FINE_DOWN_KEY = "f8"
FINE_STEP = 0.1           # langkah awal (dalam geseran roda; 1 = satu geseran penuh)
# =========================

# ---------- WinAPI ----------
u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
u32.GetAncestor.restype = wintypes.HWND
u32.WindowFromPoint.argtypes = (wintypes.POINT,)
u32.WindowFromPoint.restype = wintypes.HWND
u32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
u32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
u32.GetDoubleClickTime.restype = wintypes.UINT
u32.mouse_event.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                            wintypes.DWORD, ctypes.c_size_t)
GA_ROOT = 2
MOUSEEVENTF_WHEEL = 0x0800
FINE_UP_VK = 0x6F + int(FINE_UP_KEY[1:])        # F7 -> 0x76
FINE_DOWN_VK = 0x6F + int(FINE_DOWN_KEY[1:])    # F8 -> 0x77


def window_title(hwnd):
    n = u32.GetWindowTextLengthW(hwnd)
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def root_of(hwnd):
    return u32.GetAncestor(hwnd, GA_ROOT) if hwnd else None


# ---------- Penamaan tombol (sesuai tabel VK_CODES di bot) ----------
MODS = {"ctrl", "shift", "alt", "win"}
_SPECIAL = {
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "cmd": "win", "cmd_l": "win", "cmd_r": "win",
    "page_up": "pageup", "page_down": "pagedown",
}
for _n in ("up", "down", "left", "right", "home", "end", "insert",
           "delete", "backspace", "enter", "tab", "esc"):
    _SPECIAL[_n] = _n
for _i in range(1, 13):
    _SPECIAL[f"f{_i}"] = f"f{_i}"

_OEM = {0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
        0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}


def _vk_name(vk):
    if vk is None:
        return None
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x60 <= vk <= 0x69:                      # numpad 0-9
        return str(vk - 0x60)
    return _OEM.get(vk)


def describe(key):
    """-> (kind, name, char). kind: 'mod' | 'special' | 'char' | None (abaikan)."""
    if isinstance(key, keyboard.Key):
        if key.name == "space":
            return "char", "space", " "
        name = _SPECIAL.get(key.name)
        if name is None:
            return None, None, None
        return ("mod" if name in MODS else "special"), name, None
    char = key.char if (key.char and key.char.isprintable()) else None
    name = _vk_name(getattr(key, "vk", None)) or (char.lower() if char else None)
    if name is None:
        return None, None, None
    return "char", name, char


def ident(key):
    if isinstance(key, keyboard.Key):
        return key.name
    vk = getattr(key, "vk", None)
    return vk if vk is not None else key.char


# ---------- Format keluaran (gaya kode bot) ----------
def q(s):
    return json.dumps(s, ensure_ascii=False)


def focus_label(title):
    low = title.lower()
    for kw in FOCUS_KEYWORDS:
        if kw.lower() in low:
            return kw, False
    return title, True


def fmt_amount(raw):
    """raw = total delta roda (120 = 1 langkah). Hasil: angka untuk scroll()."""
    if raw % 120 == 0:
        return str(raw // 120), False
    return repr(round(raw / 120, 4)), True


def fmt(step, scroll_pos=True):
    kind = step[0]
    if kind == "scroll":
        _, raw, x, y = step
        amount, frac = fmt_amount(raw)
        pos = f", {x}, {y}" if scroll_pos else ""
        note = f"  # = {raw}/120 langkah roda" if frac else ""
        return f"scroll({amount}{pos}),{note}"
    if kind == "focus":
        label, full = focus_label(step[1])
        line = f"focus({q(label)}),"
        return line + ("  # judul penuh, sesuaikan/perpendek" if full else "")
    if kind == "write":
        return f"write({q(step[1])}),"
    if kind == "combo":
        keys = step[1]
        inner = ", ".join(q(k) for k in keys)
        return f"({inner},)," if len(keys) == 1 else f"({inner}),"
    if kind == "click":
        _, x, y, button, double = step
        if button == "left":
            return f"click({x}, {y}, double=True)," if double else f"click({x}, {y}),"
        if button == "right" and not double:
            return f"right_click({x}, {y}),"
        extra = ", double=True" if double else ""
        return f'click({x}, {y}{extra}, button="{button}"),'
    return f"# {step!r}"


# ---------- Aplikasi ----------
class Recorder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("460x560")
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.lock = threading.RLock()
        self.steps = []          # langkah yang sudah selesai
        self.text = []           # huruf yang sedang diketik (belum jadi write())
        self.mods = []           # modifier yang sedang ditekan (urut penekanan)
        self.down = set()        # tombol fisik yang sedang ditahan
        self.recording = False
        self.dirty = True
        self.last_hwnd = None
        self.last_click_t = 0.0
        self.opt_focus = RECORD_FOCUS
        self.toggle_req = False
        self.last_scroll_t = 0.0
        self.opt_scroll_pos = RECORD_SCROLL_POS
        self._filter_seen = False
        self.fine_step = FINE_STEP
        self.fine_q = queue.Queue()

        self.name_var = tk.StringVar(value="Rekaman")
        self.focus_var = tk.BooleanVar(value=RECORD_FOCUS)
        self.scrollpos_var = tk.BooleanVar(value=RECORD_SCROLL_POS)
        self.status = tk.StringVar()
        self.step_var = tk.StringVar(value=f"{FINE_STEP:g}")

        self._build_ui()
        self.update()
        self.own_hwnd = u32.GetAncestor(self.winfo_id(), GA_ROOT)

        self.kb = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release,
            win32_event_filter=self._kb_filter,
        )
        # Scroll dibaca langsung dari delta mentah Windows (120 = 1 geseran),
        # sehingga mouse presisi-tinggi / touchpad (nilai pecahan) ikut akurat.
        self.ms = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,                # cadangan (pynput lama)
            win32_event_filter=self._mouse_filter,
        )
        self.kb.start()
        self.ms.start()
        threading.Thread(target=self._poll_focus, daemon=True).start()
        threading.Thread(target=self._fine_worker, daemon=True).start()
        self.after(150, self._tick)

    # ----- UI -----
    def _build_ui(self):
        top = ttk.Frame(self, padding=(12, 12, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Nama tombol:").pack(side="left")
        ttk.Entry(top, textvariable=self.name_var, width=24).pack(side="left", padx=6)
        self.name_var.trace_add("write", lambda *_: setattr(self, "dirty", True))

        opt = ttk.Frame(self, padding=(12, 0))
        opt.pack(fill="x")
        ttk.Checkbutton(
            opt, text="Catat perpindahan jendela (focus)",
            variable=self.focus_var,
            command=lambda: setattr(self, "opt_focus", self.focus_var.get()),
        ).pack(side="left")
        opt2 = ttk.Frame(self, padding=(12, 0))
        opt2.pack(fill="x")
        ttk.Checkbutton(
            opt2, text="Sertakan posisi pointer pada scroll",
            variable=self.scrollpos_var,
            command=self._scrollpos_changed,
        ).pack(side="left")

        fine = ttk.Frame(self, padding=(12, 6, 12, 0))
        fine.pack(fill="x")
        ttk.Label(fine, text="Scroll halus, langkah:").pack(side="left")
        cb = ttk.Combobox(fine, textvariable=self.step_var, width=6,
                          values=["0.05", "0.1", "0.2", "0.25", "0.5", "1"])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", self._step_changed)
        cb.bind("<Return>", self._step_changed)
        cb.bind("<FocusOut>", self._step_changed)
        ttk.Label(
            fine, foreground="gray",
            text=f"{FINE_UP_KEY.upper()} ▲ / {FINE_DOWN_KEY.upper()} ▼ (tahan = terus)",
        ).pack(side="left")

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        self.btn_rec = ttk.Button(bar, text="⏺ Mulai Rekam (F9)", command=self.toggle)
        self.btn_rec.pack(side="left", fill="x", expand=True, ipady=6)
        ttk.Button(bar, text="↶ Hapus Terakhir", command=self.undo_last).pack(
            side="left", padx=(6, 0), ipady=6)
        ttk.Button(bar, text="🗑 Semua", command=self.clear_all).pack(
            side="left", padx=(6, 0), ipady=6)

        ttk.Label(self, textvariable=self.status, foreground="gray").pack(
            fill="x", padx=12)

        box = ttk.Frame(self, padding=(12, 6))
        box.pack(fill="both", expand=True)
        self.txt = tk.Text(box, wrap="none", font=("Consolas", 10), height=14)
        sy = ttk.Scrollbar(box, orient="vertical", command=self.txt.yview)
        sx = ttk.Scrollbar(box, orient="horizontal", command=self.txt.xview)
        self.txt.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self.txt.pack(side="left", fill="both", expand=True)

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="📋 Salin", command=self.copy).pack(
            side="left", fill="x", expand=True, ipady=4)
        ttk.Button(bottom, text="💾 Simpan .txt", command=self.save).pack(
            side="left", fill="x", expand=True, padx=(6, 0), ipady=4)

    def _step_changed(self, *_):
        try:
            v = float(self.step_var.get().replace(",", "."))
        except ValueError:
            v = self.fine_step
        v = min(5.0, max(1 / 120, v))
        self.fine_step = v
        self.step_var.set(f"{v:g}")

    def _scrollpos_changed(self):
        self.opt_scroll_pos = self.scrollpos_var.get()
        self.dirty = True

    # ----- Kontrol -----
    def toggle(self):
        with self.lock:
            if self.recording:
                self._flush_text()
                self.recording = False
            else:
                self.last_hwnd = None
                self.last_click_t = 0.0
                self.recording = True
            self.dirty = True
        self.btn_rec.config(
            text="⏹ Berhenti (F9)" if self.recording else "⏺ Mulai Rekam (F9)")

    def undo_last(self):
        with self.lock:
            if self.text:
                self.text.clear()
            elif self.steps:
                self.steps.pop()
            self.dirty = True

    def clear_all(self):
        with self.lock:
            self.steps.clear()
            self.text.clear()
            self.dirty = True

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.txt.get("1.0", "end-1c"))
        self.status.set("Tersalin ke clipboard ✓")

    def save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile="rekaman_langkah.txt",
            filetypes=[("Teks", "*.txt"), ("Semua file", "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt.get("1.0", "end-1c") + "\n")
            self.status.set(f"Tersimpan: {path}")

    def _close(self):
        try:
            self.kb.stop()
            self.ms.stop()
        finally:
            self.destroy()

    # ----- Render & refresh -----
    def _render(self):
        with self.lock:
            steps = list(self.steps)
            pending = "".join(self.text)
        lines, prev = [], None
        for s in steps:
            line = fmt(s, self.opt_scroll_pos)
            if s[0] == "focus" and line == prev:      # focus ganda berurutan
                continue
            lines.append(line)
            prev = line
        if pending:
            lines.append(f"write({q(pending)}),")
        body = "\n".join("    " + l for l in lines)
        return f"({q(self.name_var.get() or 'Rekaman')}, [\n{body}\n]),"

    def _tick(self):
        if self.toggle_req:
            self.toggle_req = False
            self.toggle()
        if self.dirty:
            self.dirty = False
            code = self._render()
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", code)
            if self.recording:
                self.txt.see("end")
        with self.lock:
            n = len(self.steps) + (1 if self.text else 0)
        if self.recording:
            self.status.set(f"● MEREKAM — {n} langkah. Tekan F9 untuk berhenti.")
        elif not self.status.get().startswith(("Tersalin", "Tersimpan")):
            self.status.set(f"Siap — {n} langkah. Tekan F9 untuk mulai.")
        self.after(150, self._tick)

    # ----- Pencatatan -----
    def _flush_text(self):
        if self.text:
            self.steps.append(("write", "".join(self.text)))
            self.text.clear()

    def _emit(self, step):
        with self.lock:
            self._flush_text()
            self.steps.append(step)
            self.dirty = True

    def _note_window(self, hwnd):
        if not hwnd or hwnd == self.own_hwnd:
            return
        with self.lock:
            if hwnd == self.last_hwnd:
                return
            title = window_title(hwnd)
            if not title:                 # taskbar, tooltip, dll.
                return
            self.last_hwnd = hwnd
            self._flush_text()
            self.steps.append(("focus", title))
            self.dirty = True

    def _poll_focus(self):
        while True:
            time.sleep(0.15)
            if self.recording and self.opt_focus:
                self._note_window(u32.GetForegroundWindow())

    # ----- Keyboard -----
    def _on_press(self, key):
        try:
            idt = ident(key)
            repeat = idt in self.down
            self.down.add(idt)
            if repeat:                       # abaikan auto-repeat saat ditahan
                return
            if key == HOTKEY:
                self.toggle_req = True
                return
            if (self.recording and isinstance(key, keyboard.Key)
                    and key.name in (FINE_UP_KEY, FINE_DOWN_KEY)):
                return                       # tombol scroll halus, bukan langkah

            kind, name, char = describe(key)
            if kind == "mod":
                if name not in self.mods:
                    self.mods.append(name)
                return
            if kind is None or not self.recording:
                return
            fg = u32.GetForegroundWindow()
            if fg == self.own_hwnd:          # sedang mengetik di jendela perekam
                return
            if self.opt_focus:
                self._note_window(fg)

            mods = list(self.mods)
            if kind == "char":
                if any(m in mods for m in ("ctrl", "alt", "win")):
                    self._emit(("combo", tuple(mods + [name])))
                elif char:
                    with self.lock:
                        self.text.append(char)
                        self.dirty = True
                else:
                    self._emit(("combo", tuple(mods + [name])))
            elif name == "backspace" and not mods:
                with self.lock:
                    if self.text:            # koreksi typo: hapus huruf terakhir
                        self.text.pop()
                        self.dirty = True
                        return
                self._emit(("combo", ("backspace",)))
            else:
                self._emit(("combo", tuple(mods + [name])))
        except Exception as e:               # jangan sampai listener mati
            print("on_press error:", e)

    def _on_release(self, key):
        try:
            self.down.discard(ident(key))
            kind, name, _ = describe(key)
            if kind == "mod" and name in self.mods:
                self.mods.remove(name)
        except Exception as e:
            print("on_release error:", e)

    # ----- Mouse (hanya klik, tanpa pergerakan) -----
    def _on_click(self, x, y, button, pressed):
        try:
            if not pressed or not self.recording:
                return
            bname = getattr(button, "name", "")
            if bname not in ("left", "right", "middle"):
                return
            x, y = int(x), int(y)
            hwnd = root_of(u32.WindowFromPoint(wintypes.POINT(x, y)))
            if hwnd and hwnd == self.own_hwnd:   # klik di jendela perekam
                return
            if self.opt_focus:
                self._note_window(hwnd)

            now = time.time()
            dbl_t = u32.GetDoubleClickTime() / 1000.0
            tol = max(4, u32.GetSystemMetrics(36))   # SM_CXDOUBLECLK
            with self.lock:
                self._flush_text()
                last = self.steps[-1] if self.steps else None
                if (last and last[0] == "click" and not last[4]
                        and last[3] == bname
                        and now - self.last_click_t <= dbl_t
                        and abs(last[1] - x) <= tol and abs(last[2] - y) <= tol):
                    self.steps[-1] = ("click", last[1], last[2], bname, True)
                else:
                    self.steps.append(("click", x, y, bname, False))
                self.last_click_t = now
                self.dirty = True
        except Exception as e:
            print("on_click error:", e)


    # ----- Scroll halus (F7/F8) -----
    def _kb_filter(self, msg, data):
        if self.recording and data.vkCode in (FINE_UP_VK, FINE_DOWN_VK):
            if msg in (0x0100, 0x0104):                  # tombol ditekan / auto-repeat
                direction = 1 if data.vkCode == FINE_UP_VK else -1
                delta = max(1, round(self.fine_step * 120)) * direction
                self.fine_q.put(delta)                   # dikirim oleh thread lain
            self.kb.suppress_event()                     # aplikasi tidak menerima F7/F8
        return True

    def _fine_worker(self):
        while True:
            delta = self.fine_q.get()
            try:
                # Event roda asli dengan delta kecil -> ditangkap hook mouse
                # dan direkam seperti scroll biasa.
                u32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta & 0xFFFFFFFF, 0)
            except Exception as e:
                print("fine scroll error:", e)

    # ----- Scroll (digabung per rentetan geseran) -----
    def _mouse_filter(self, msg, data):
        if msg == 0x020A:                     # WM_MOUSEWHEEL
            self._filter_seen = True
            try:
                raw = ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value
                self._handle_wheel(int(data.pt.x), int(data.pt.y), raw)
            except Exception as e:
                print("wheel error:", e)
        return True                           # jangan blokir event ke aplikasi

    def _on_scroll(self, x, y, dx, dy):
        if self._filter_seen:                 # sudah ditangani oleh filter
            return
        self._handle_wheel(int(x), int(y), int(round(dy * 120)))

    def _handle_wheel(self, x, y, raw):
        """raw > 0 = scroll ke atas, raw < 0 = ke bawah (120 = 1 langkah roda)."""
        if not self.recording or raw == 0:
            return
        hwnd = root_of(u32.WindowFromPoint(wintypes.POINT(x, y)))
        if hwnd and hwnd == self.own_hwnd:    # scroll di jendela perekam
            return
        now = time.time()
        with self.lock:
            last = self.steps[-1] if self.steps else None
            if (last and last[0] == "scroll" and not self.text
                    and now - self.last_scroll_t <= SCROLL_GAP
                    and (last[1] > 0) == (raw > 0)
                    and abs(last[2] - x) <= SCROLL_POS_TOL
                    and abs(last[3] - y) <= SCROLL_POS_TOL):
                self.steps[-1] = ("scroll", last[1] + raw, last[2], last[3])
            else:
                self._flush_text()
                self.steps.append(("scroll", raw, x, y))
            self.last_scroll_t = now
            self.dirty = True


if __name__ == "__main__":
    Recorder().mainloop()
