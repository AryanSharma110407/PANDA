"""
PANDA Vision — Layer 2: Windows Native OCR Engine
==================================================
Uses the `winocr` library (which wraps the native Windows Media OCR API)
to perform extremely fast, offline, and lightweight OCR.

Requires Windows 10+ and no external binaries (unlike Tesseract).
Uses negligible RAM and CPU.

"""

import os
# pyrefly: ignore [missing-import]
from PIL import Image

try:
    # pyrefly: ignore [missing-import]
    import winocr
    _WINOCR_AVAILABLE = True
except ImportError:
    winocr = None
    _WINOCR_AVAILABLE = False
    print("  \033[31m[WinOCR] winocr library is not installed. Run: pip install winocr\033[0m", flush=True)


def read_image(image: Image.Image) -> list[dict]:
    """
    Reads text from a PIL Image using Windows Native OCR (via winocr)
    and returns structured results in the same format as legacy PaddleOCR.
    """
    # Respect DISABLE_OCR environment variable (default to 0 / enabled)
    if os.getenv("DISABLE_OCR", "0") == "1":
        return []

    if not _WINOCR_AVAILABLE or winocr is None:
        return []

    try:
        # Run Windows native OCR synchronously
        result = winocr.recognize_pil_sync(image)
        
        parsed_results = []
        for line in result.get("lines", []):
            line_text = line.get("text", "").strip()
            words = line.get("words", [])
            if not words or not line_text:
                continue

            x_coords = []
            y_coords = []
            for w in words:
                rect = w.get("bounding_rect", {})
                x = rect.get("x", 0)
                y = rect.get("y", 0)
                width = rect.get("width", 0)
                height = rect.get("height", 0)

                x_coords.extend([x, x + width])
                y_coords.extend([y, y + height])

            if x_coords and y_coords:
                bbox = [float(min(x_coords)), float(min(y_coords)), float(max(x_coords)), float(max(y_coords))]
            else:
                bbox = [0.0, 0.0, 0.0, 0.0]

            import re
            
            conf = 1.0
            # Penalize pure special characters
            if not re.search(r'[a-zA-Z0-9]', line_text):
                conf -= 0.4
                
            # Penalize mixed alpha-symbol garbage (e.g. Subm!t)
            if len(line_text) > 0:
                non_word_chars = len(re.findall(r'[^a-zA-Z0-9\s]', line_text))
                if (non_word_chars / len(line_text)) > 0.3:
                    conf -= 0.2
                    
            # Penalize weirdly sized bounding boxes
            box_width = bbox[2] - bbox[0]
            box_height = bbox[3] - bbox[1]
            if box_height < 6 or box_width < 6:
                conf -= 0.3
            elif box_height > 200 or box_width > 800:
                conf -= 0.2
                
            conf = max(0.1, round(conf, 2))

            parsed_results.append({
                "text": line_text,
                "confidence": conf,
                "bbox": bbox
            })
            
        return parsed_results
    except Exception as e:
        print(f"  \033[31m[WinOCR] OCR error: {e}\033[0m", flush=True)
        return []


def read_screen() -> list[dict]:
    """Captures the primary monitor screen and reads all text."""
    from .screenshot_manager import capture_screen
    img = capture_screen()
    return read_image(img)


def read_region(x: int, y: int, w: int, h: int) -> list[dict]:
    """Captures a specific region of the screen and reads text within it."""
    from .screenshot_manager import capture_region
    img = capture_region(x, y, w, h)
    return read_image(img)


# ─── Backward Compatibility Layer ─────────────────────────────────────────────

def _get_ocr_model():
    """Compatibility stub for PaddleOCR model checker in legacy tests."""
    return "winocr"

