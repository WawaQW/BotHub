import sys
import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui

# ====== KONFIGURASI ======
START_DELAY = 0.1
STEP_DELAY = 0.1
KEY_HOLD = 0.05      # lama menahan tiap tombol (detik); naikkan jika AutoCAD kadang tidak merespons
WHEEL_DELTA = 120 if sys.platform == "win32" else 1   # 1 langkah roda mouse di Windows


# ----- Helper untuk langkah selain hotkey -----
def click(x=None, y=None, double=False):
    """Klik kiri di koordinat layar (x, y). double=True untuk klik ganda.
    Tanpa koordinat, click() mengklik di posisi pointer saat ini."""
    return {"type": "click", "x": x, "y": y, "double": double}


def move(x, y, duration=0.0):
    """Pindahkan pointer ke (x, y) TANPA klik."""
    return {"type": "move", "x": x, "y": y, "duration": duration}


def scroll(amount, x=None, y=None, duration=0.0):
    """Scroll mouse. amount = jumlah langkah roda (boleh desimal).
    Positif = ke atas, negatif = ke bawah. Jika x, y diisi, pointer dipindah
    dulu ke sana (tanpa klik)."""
    return {"type": "scroll", "amount": amount, "x": x, "y": y, "duration": duration}


def wait(sec):
    """Tunggu sekian detik."""
    return {"type": "wait", "sec": sec}


def focus(title):
    """Aktifkan jendela yang judulnya mengandung `title` (tanpa tombol Win).
    Huruf besar/kecil tidak berpengaruh. Khusus Windows."""
    return {"type": "focus", "title": title}


def tab(name, max_tabs=15):
    """Pilih tab gambar AutoCAD yang judulnya mengandung `name` (mis. "TONGGORISA"
    atau "23061605_TONGGORISA.dwg"). Jendela AutoCAD harus sudah aktif (pakai
    focus() dulu). Tab ditelusuri dengan Ctrl+Tab maksimal `max_tabs` kali.
    Huruf besar/kecil tidak berpengaruh. Khusus Windows."""
    return {"type": "tab", "name": name, "max_tabs": max_tabs}


def write(text, interval=0.03):
    """Ketik teks biasa (misalnya perintah AutoCAD seperti "FIND")."""
    return {"type": "write", "text": text, "interval": interval}


# ----- Kode tombol virtual Windows (dipakai untuk pengiriman tombol langsung) -----
VK_CODES = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "delete": 0x2E, "backspace": 0x08,
    "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "space": 0x20,
}
VK_CODES.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})
VK_CODES.update({f"f{i}": 0x6F + i for i in range(1, 13)})
# Tombol "extended": panah, Home/End, PageUp/Down, Insert/Delete, Win
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C}


# ====== DAFTAR TOMBOL ======
# Judul jendela AutoCAD biasanya "Autodesk AutoCAD 2024 - [nama.dwg]".
# Sesuaikan teks di focus() dengan title bar AutoCAD Anda.
BUTTONS = [
    ("Find", [focus("Edge"),("ctrl", "1"),("ctrl", "c"),focus("Autodesk AutoCAD"),("ctrl", "up"),("ctrl", "v"),("alt", "f"),("esc",)]),
    ("Boudery", [focus("Autodesk AutoCAD"), ("ctrl", "down"), ("enter",), wait(0.5), click(834,373),("enter",)]),
    # ("Bordery", [focus("Autodesk AutoCAD"),scroll(-50, 841, 323),("ctrl", "down"),("enter",),click(841, 323),("enter",),]),
    ("Paste Persil", [focus("Autodesk AutoCAD"),("ctrl", "c"),("ctrl", "tab"),("ctrl", "v"),move(1209, 70),]),
    ("Konfirmasi Persil", [focus("Autodesk AutoCAD"),("ctrl", "c"),("ctrl", "tab"),("ctrl", "v"),wait(0.5),tab("23061605_TONGGORISA.dwg"),focus("Edge"),click(803, 207),click(875, 296),("down",),move(1229, 71),]),
    ("Gettile", [focus("Autodesk AutoCAD"), ("gettile"), ("enter",), wait(0.5), ("tab",), ("tab",), ("down",), ("tab",), ("tab",), ("tab",), ("tab",),("enter",) ]),
    ("Move", [focus("Autodesk AutoCAD"),("m"), ("enter",),]),
]
# =========================

pyautogui.FAILSAFE = True  # Gerakkan mouse ke pojok kiri atas untuk membatalkan


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class HotkeyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BPN AutoCAD Fast" + (" [Admin]" if is_admin() else ""))
        self.geometry("320x" + str(90 + 55 * (len(BUTTONS) + 2)))
        self.attributes("-topmost", True)
        self.after(100, self._no_focus)
        self.resizable(False, False)
        self.status = tk.StringVar(value="MagangHub Kantah Bima")
        self.busy = False

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        for label, sequence in BUTTONS:
            ttk.Button(
                frame,
                text=label,
                command=lambda s=sequence, l=label: self.run_sequence(l, s),
            ).pack(fill="x", pady=5, ipady=8)

        ttk.Button(
            frame, text="📍 Cek Posisi Mouse (3 detik)", command=self.pick_position
        ).pack(fill="x", pady=(15, 5), ipady=4)

        ttk.Button(
            frame, text="🔎 Info Jendela Aktif (3 detik)", command=self.inspect_window
        ).pack(fill="x", pady=5, ipady=4)

        ttk.Label(
            frame, textvariable=self.status, foreground="gray",
            wraplength=290, justify="center",
        ).pack(side="bottom", pady=(10, 0))

    # ---------- Menjalankan urutan ----------
    def run_sequence(self, label, sequence):
        if self.busy:
            return
        self.busy = True
        threading.Thread(
            target=self._worker, args=(label, sequence), daemon=True
        ).start()

    def _worker(self, label, sequence):
        try:
            self._set_status(f"Menjalankan: {label}")
            time.sleep(START_DELAY)
            for step in sequence:
                if isinstance(step, dict):
                    kind = step["type"]
                    if kind == "click":
                        x, y = step["x"], step["y"]
                        pyautogui.click(x, y, clicks=2 if step["double"] else 1)
                        where = "posisi pointer" if x is None else f"({x}, {y})"
                        self._set_status(f"Klik: {where}")
                    elif kind == "move":
                        pyautogui.moveTo(step["x"], step["y"], duration=step["duration"])
                        self._set_status(f"Pointer ke: ({step['x']}, {step['y']})")
                    elif kind == "scroll":
                        if step["x"] is not None:
                            pyautogui.moveTo(step["x"], step["y"], duration=step["duration"])
                            time.sleep(0.1)
                        remaining = int(step["amount"] * WHEEL_DELTA)
                        limit = 30 * WHEEL_DELTA          # maks 30 langkah per event
                        while remaining != 0:
                            chunk = max(-limit, min(limit, remaining))
                            pyautogui.scroll(chunk)
                            remaining -= chunk
                        self._set_status(f"Scroll: {step['amount']}")
                    elif kind == "wait":
                        self._set_status(f"Tunggu {step['sec']} detik")
                        time.sleep(step["sec"])
                    elif kind == "focus":
                        self._set_status(f"Pindah ke: {step['title']}")
                        self._focus_window(step["title"])
                    elif kind == "tab":
                        self._set_status(f"Pilih tab: {step['name']}")
                        self._switch_tab(step["name"], step["max_tabs"])
                    elif kind == "write":
                        self._set_status(f"Mengetik: {step['text']}")
                        self._type_text(step["text"], step["interval"])
                    else:
                        raise ValueError(f"Langkah tidak dikenal: {kind}")
                else:
                    self._press_combo(step)
                    self._set_status("Menekan: " + "+".join(step).upper())
                time.sleep(STEP_DELAY)
            self._set_status("Selesai ✓")
        except Exception as e:
            self._set_status(f"Error: {e}")
        finally:
            self.busy = False

    # ---------- Pengiriman tombol ----------
    def _key_event(self, key, up=False):
        """Kirim satu event tombol lengkap dengan scan code dan flag extended
        (penting untuk tombol panah agar dikenali aplikasi seperti AutoCAD)."""
        vk = VK_CODES[key]
        flags = 0x0001 if vk in EXTENDED_VKS else 0   # KEYEVENTF_EXTENDEDKEY
        if up:
            flags |= 0x0002                           # KEYEVENTF_KEYUP
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        ctypes.windll.user32.keybd_event(vk, scan, flags, 0)

    def _press_combo(self, keys):
        keys = [k.lower() for k in keys]
        if sys.platform != "win32" or any(k not in VK_CODES for k in keys):
            pyautogui.hotkey(*keys)        # cadangan untuk tombol yang tidak ada di tabel
            return
        for k in keys:
            self._key_event(k)
            time.sleep(KEY_HOLD)
        for k in reversed(keys):
            self._key_event(k, up=True)
            time.sleep(0.02)

    def _type_text(self, text, interval=0.03):
        for ch in text:
            key = "space" if ch == " " else ch.lower()
            if sys.platform == "win32" and key in VK_CODES and (ch.isalnum() or ch == " "):
                self._press_combo((key,))
            else:
                pyautogui.write(ch)
            time.sleep(interval)

    # ---------- Pindah jendela ----------
    def _focus_window(self, part, timeout=3.0):
        """Aktifkan jendela berdasarkan potongan judul (khusus Windows)."""
        if sys.platform != "win32":
            raise RuntimeError("focus() hanya untuk Windows")
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        found = []

        def callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    if part.lower() in buf.value.lower():
                        found.append(hwnd)
            return True

        enum_proc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
        )
        user32.EnumWindows(enum_proc(callback), 0)
        if not found:
            raise RuntimeError(f"Jendela '{part}' tidak ditemukan")
        hwnd = found[0]

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)   # SW_RESTORE

        # Agar Windows mengizinkan pindah fokus dari proses lain
        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        my_tid = kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(my_tid, fg_tid, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(my_tid, fg_tid, False)

        end = time.time() + timeout
        while time.time() < end:
            if user32.GetForegroundWindow() == hwnd:
                return
            time.sleep(0.05)
        raise RuntimeError(f"Gagal berpindah ke '{part}'")

    # ---------- Pindah tab gambar AutoCAD ----------
    def _foreground_title(self):
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _switch_tab(self, name, max_tabs=15):
        """Tekan Ctrl+Tab sampai judul AutoCAD (berisi nama gambar aktif)
        mengandung `name`."""
        if sys.platform != "win32":
            raise RuntimeError("tab() hanya untuk Windows")
        target = name.lower()
        if target in self._foreground_title().lower():
            return                                   # sudah di tab yang benar
        for _ in range(max_tabs):
            self._press_combo(("ctrl", "tab"))
            time.sleep(0.4)                          # beri waktu AutoCAD ganti tab
            if target in self._foreground_title().lower():
                return
        raise RuntimeError(f"Tab '{name}' tidak ditemukan")

    # ---------- Info jendela aktif (diagnosis) ----------
    def inspect_window(self):
        if self.busy:
            return
        if sys.platform != "win32":
            self._set_status("Hanya untuk Windows")
            return
        self.busy = True
        threading.Thread(target=self._inspect_worker, daemon=True).start()

    def _inspect_worker(self):
        try:
            for i in range(3, 0, -1):
                self._set_status(f"Klik jendela AutoCAD sekarang... {i}")
                time.sleep(1)
            info = self._describe_foreground()
            self._set_status("Info jendela siap (tersalin)")
            self.after(0, lambda: self._show_info(info))
        except Exception as e:
            self._set_status(f"Error: {e}")
        finally:
            self.busy = False

    def _show_info(self, info):
        self._copy_to_clipboard(info)
        messagebox.showinfo("Info Jendela Aktif", info)

    def _describe_foreground(self):
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        a32 = ctypes.WinDLL("advapi32", use_last_error=True)
        u32.GetForegroundWindow.restype = wintypes.HWND
        u32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        u32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        u32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        u32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        )
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        k32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        a32.OpenProcessToken.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
        )
        a32.GetTokenInformation.argtypes = (
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )

        hwnd = u32.GetForegroundWindow()
        n = u32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, title, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        exe = "?"
        window_elevated = None        # True / False / None (tidak bisa dibaca)
        hproc = k32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFORMATION
        if hproc:
            size = wintypes.DWORD(520)
            path = ctypes.create_unicode_buffer(520)
            if k32.QueryFullProcessImageNameW(hproc, 0, path, ctypes.byref(size)):
                exe = path.value.rsplit("\\", 1)[-1]
            htok = wintypes.HANDLE()
            if a32.OpenProcessToken(hproc, 0x0008, ctypes.byref(htok)):   # TOKEN_QUERY
                val = wintypes.DWORD()
                ret = wintypes.DWORD()
                if a32.GetTokenInformation(      # 20 = TokenElevation
                    htok, 20, ctypes.byref(val), ctypes.sizeof(val), ctypes.byref(ret)
                ):
                    window_elevated = bool(val.value)
                k32.CloseHandle(htok)
            k32.CloseHandle(hproc)

        py_admin = is_admin()
        if window_elevated is None:
            elev_txt = "tidak bisa dibaca (kemungkinan berjalan sebagai Administrator)"
        else:
            elev_txt = "YA (Administrator)" if window_elevated else "tidak"
        lines = [
            f"Judul   : {title.value}",
            f"Kelas   : {cls.value}",
            f"Proses  : {exe} (PID {pid.value})",
            f"Jendela elevated : {elev_txt}",
            f"Python elevated  : {'YA' if py_admin else 'tidak'}",
        ]
        if (window_elevated is not False) and not py_admin:
            lines += [
                "",
                "PERHATIAN: jendela ini kemungkinan berjalan sebagai Administrator,",
                "sedangkan Python tidak. Windows memblokir input dari Python ke",
                "jendela itu. Jalankan Python/terminal sebagai Administrator.",
            ]
        return "\n".join(lines)

    # ---------- Pengambil posisi mouse ----------
    def pick_position(self):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._pick_worker, daemon=True).start()

    def _pick_worker(self):
        try:
            for i in range(3, 0, -1):
                self._set_status(f"Arahkan mouse ke kolom input... {i}")
                time.sleep(1)
            x, y = pyautogui.position()
            text = f"click({x}, {y})"
            self._set_status(f"Posisi: {text} (tersalin)")
            self.after(0, lambda: self._copy_to_clipboard(text))
        finally:
            self.busy = False

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    # ---------- Util ----------
    def _set_status(self, text):
        self.after(0, lambda: self.status.set(text))

    def _no_focus(self):
        """Jendela tidak mengambil fokus saat diklik (khusus Windows)."""
        if sys.platform != "win32":
            return
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE
        )


if __name__ == "__main__":
    HotkeyApp().mainloop()