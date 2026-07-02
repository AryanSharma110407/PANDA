import sys
import os
import pprint

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision.screenshot_manager import capture_screen
import winocr

img = capture_screen()
result = winocr.recognize_pil_sync(img)

print("Keys in result dict:")
print(result.keys())

print("\nResult dictionary content:")
pprint.pprint(result)
