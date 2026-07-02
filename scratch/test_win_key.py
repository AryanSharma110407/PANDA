import pyautogui
import time
print("Pressing win key in 2 seconds...")
time.sleep(2)
pyautogui.press("win")
print("Pressed win key.")
time.sleep(1)
pyautogui.typewrite("notepad", interval=0.1)
print("Typed notepad.")
time.sleep(1)
pyautogui.press("enter")
print("Pressed enter.")
