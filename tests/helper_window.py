"""A stand-in for the user's game: a normal window in ANOTHER process that grabs
the foreground. Used to prove our overlay never steals focus from it.

Writes its HWND to argv[1] so the test can identify it.
"""
import sys
import time
import tkinter as tk
from ctypes import windll

r = tk.Tk()
r.title("HELPER-FOREGROUND")
r.geometry("340x140+120+120")
tk.Label(r, text="pretend game window").pack(expand=True)
r.update()
r.lift()
r.focus_force()
r.update()

u = windll.user32
hwnd = u.GetParent(r.winfo_id()) or r.winfo_id()
with open(sys.argv[1], "w") as fh:
    fh.write(str(int(hwnd)))

t = time.time()
while time.time() - t < 25:
    r.update()
    time.sleep(0.03)
