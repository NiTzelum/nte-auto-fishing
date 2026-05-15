"""
Авторыбалка v7 — удержание клавиш через DirectInput (win32api)
F6  — старт/стоп
F7  — RGB под курсором
F8  — сохранить скриншот полоски
F9  — сохранить полный экран
ESC — выход
"""

import time, threading, os
import numpy as np
import mss as mss_module
import win32api, win32con
from pynput import keyboard as kb
from PIL import Image as PILImage

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
BAR_X1     = 612   # левый край полоски (из F7)
BAR_X2     = 1312  # правый край полоски (из F7)
BAR_Y      = 55    # верхний край (чуть ниже верха полоски)
BAR_HEIGHT = 20    # высота захвата

# Цвета из bar_debug.png
ZONE_COLOR   = (162, 181,  34)  # жёлто-зелёная зона
MARKER_COLOR = (159, 246, 254)  # голубой маркер
TOLERANCE    = 25               # допуск ±

INTERVAL  = 0.04
DEAD_ZONE = 0.025
KEY_LEFT  = 'a'
KEY_RIGHT = 'd'

# DirectInput скан-коды
DI_SCANCODES = {
    'a': 0x1E,
    'd': 0x20,
}
# ──────────────────────────────────────────────────────────────────────────────

running = False
sct = mss_module.mss()
_current_key = None  # какая клавиша сейчас зажата


def get_region():
    return {'top': BAR_Y, 'left': BAR_X1, 'width': BAR_X2 - BAR_X1, 'height': BAR_HEIGHT}


def color_match(pixel, target, tol=TOLERANCE):
    return all(abs(int(pixel[i]) - int(target[i])) <= tol for i in range(3))


def scan_bar():
    shot = sct.grab(get_region())
    img = np.array(shot)[:, :, :3]
    bar_w = img.shape[1]
    marker_xs, zone_xs = [], []

    for x in range(bar_w):
        col = img[:, x, :]
        for row in col:
            if color_match(row, MARKER_COLOR):
                marker_xs.append(x)
                break
            if color_match(row, ZONE_COLOR):
                zone_xs.append(x)
                break

    marker = (sum(marker_xs) / len(marker_xs) / bar_w) if marker_xs else None
    zl = (min(zone_xs) / bar_w) if zone_xs else None
    zr = (max(zone_xs) / bar_w) if zone_xs else None
    return marker, zl, zr


def hold_key(key):
    """Зажать клавишу через DirectInput. Если уже зажата — не трогать."""
    global _current_key
    if _current_key == key:
        return  # уже держим эту клавишу
    if _current_key is not None:
        # отпустить предыдущую
        sc = DI_SCANCODES[_current_key]
        win32api.keybd_event(0, sc, win32con.KEYEVENTF_SCANCODE | win32con.KEYEVENTF_KEYUP, 0)
        print(f"  [ОТПУСТИЛ '{_current_key}']")
    # зажать новую
    sc = DI_SCANCODES[key]
    win32api.keybd_event(0, sc, win32con.KEYEVENTF_SCANCODE, 0)
    _current_key = key
    print(f"  [ЗАЖАЛ '{key}']")


def release_all():
    """Отпустить текущую зажатую клавишу."""
    global _current_key
    if _current_key is not None:
        sc = DI_SCANCODES[_current_key]
        win32api.keybd_event(0, sc, win32con.KEYEVENTF_SCANCODE | win32con.KEYEVENTF_KEYUP, 0)
        print(f"  [ОТПУСТИЛ '{_current_key}']")
        _current_key = None


def bot_loop():
    global running
    print("[БОТ] Запущен!\n")
    i = 0
    while running:
        try:
            marker, zl, zr = scan_bar()
            i += 1
            if marker is None or zl is None or zr is None:
                release_all()
                print(f"[{i}] НЕТ ДАННЫХ: маркер={marker} зл={zl} зп={zr}")
                time.sleep(0.1)
                continue
            zone_center = (zl + zr) / 2
            error = marker - zone_center
            pct = lambda v: f"{v*100:.1f}%"
            if abs(error) > DEAD_ZONE:
                key = KEY_LEFT if error > 0 else KEY_RIGHT
                print(f"[{i}] ДЕРЖУ '{key}'  маркер={pct(marker)} центр={pct(zone_center)} ошибка={error*100:+.1f}%")
                hold_key(key)
            else:
                release_all()
                print(f"[{i}] OK  маркер={pct(marker)} центр={pct(zone_center)} ошибка={error*100:+.1f}%")
        except Exception as e:
            print(f"\n[ОШИБКА] {e}")
        time.sleep(INTERVAL)
    release_all()
    print("\n[БОТ] Остановлен.")


def toggle():
    global running
    if not running:
        running = True
        threading.Thread(target=bot_loop, daemon=True).start()
        print("[F6] Старт\n")
    else:
        running = False
        print("\n[F6] Стоп")


def calibrate():
    import ctypes
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    x, y = pt.x, pt.y
    shot = sct.grab({'top': y, 'left': x, 'width': 1, 'height': 1})
    px = np.array(shot)[0, 0, :3]
    print(f"\n[F7] ({x},{y}) RGB=({px[0]},{px[1]},{px[2]})")


def debug_save():
    shot = sct.grab(get_region())
    img = np.array(shot)[:, :, :3]
    pil = PILImage.fromarray(img)
    pil = pil.resize((pil.width * 5, pil.height * 5), PILImage.NEAREST)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bar_debug.png")
    pil.save(path)
    print(f"\n[F8] Сохранено: {path}")
    print("[F8] RGB по центру (каждые 40px):")
    bar_w = img.shape[1]
    mid_y = img.shape[0] // 2
    for x in range(0, bar_w, 40):
        px = img[mid_y, x, :]
        print(f"  x={x:4d} ({x*100//bar_w:3d}%) → RGB({px[0]:3d},{px[1]:3d},{px[2]:3d})")


def fullscreen_save():
    shot = sct.grab(sct.monitors[1])
    img = np.array(shot)[:, :, :3]
    pil = PILImage.fromarray(img)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fullscreen_debug.png")
    pil.save(path)
    mon = sct.monitors[1]
    print(f"\n[F9] Полный экран сохранён: {path}  ({mon['width']}x{mon['height']})")


def on_press(key):
    global running
    try:
        if key == kb.Key.f6:    toggle()
        elif key == kb.Key.f7:  calibrate()
        elif key == kb.Key.f8:  debug_save()
        elif key == kb.Key.f9:  fullscreen_save()
        elif key == kb.Key.f4:
            running = False
            release_all()
            return False
    except Exception as e:
        print(f"[ОШИБКА hotkey] {e}")


print("=" * 55)
print("  Авторыбалка бот v7")
print("  F6  — старт / стоп")
print("  F7  — RGB под курсором")
print("  F8  — скриншот полоски (bar_debug.png)")
print("  F9  — полный экран (fullscreen_debug.png)")
print("  F4 — выход")
print("=" * 55)
print(f"\n  Полоска: X=[{BAR_X1}-{BAR_X2}]  Y={BAR_Y}  H={BAR_HEIGHT}")
print(f"  Маркер (голубой):  RGB{MARKER_COLOR} ±{TOLERANCE}")
print(f"  Зона (жёлто-зел.): RGB{ZONE_COLOR} ±{TOLERANCE}")
print("\nОжидаю F6...\n")

with kb.Listener(on_press=on_press) as listener:
    listener.join()
running = False
release_all()
print("Выход.")
