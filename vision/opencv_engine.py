import os
# pyrefly: ignore [missing-import]
import cv2
import numpy as np
# pyrefly: ignore [missing-import]
from PIL import Image

def find_image_on_screen(template_path: str, threshold: float = 0.8) -> dict | None:
    """
    Finds a template image on the current screen using cv2.matchTemplate.
    Returns details of the match if found and above threshold, otherwise None.
    """
    from vision.screenshot_manager import capture_screen
    
    if not os.path.exists(template_path):
        print(f"  [OpenCV] Template file not found: {template_path}")
        return None
        
    try:
        screen_img = capture_screen()
        # Convert screen to cv2 format (BGR)
        screen_cv = cv2.cvtColor(np.array(screen_img), cv2.COLOR_RGB2BGR)
        
        # Read template image in BGR
        template_cv = cv2.imread(template_path)
        if template_cv is None:
            print(f"  [OpenCV] Failed to read template image: {template_path}")
            return None
            
        h, w = template_cv.shape[:2]
        
        # Match Template
        res = cv2.matchTemplate(screen_cv, template_cv, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val >= threshold:
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return {
                "found": True,
                "x": int(center_x),
                "y": int(center_y),
                "confidence": float(max_val),
                "bbox": [int(max_loc[0]), int(max_loc[1]), int(max_loc[0] + w), int(max_loc[1] + h)]
            }
    except Exception as e:
        print(f"  [OpenCV] Error during template matching: {e}")
        
    return None

def find_buttons(image: Image.Image) -> list[dict]:
    """Locates structural buttons via edge/contour analysis."""
    try:
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        buttons = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = w / float(h)
            # Buttons are typically small to medium rectangles with standard ratios
            if 40 <= w <= 400 and 15 <= h <= 100 and 1.2 <= aspect_ratio <= 6.0:
                buttons.append({
                    "type": "button",
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "width": int(w),
                    "height": int(h)
                })
        return buttons
    except Exception as e:
        print(f"  [OpenCV] Error finding buttons: {e}")
        return []

def find_text_regions(image: Image.Image) -> list[dict]:
    """Locates structural text zones via morphological operations."""
    try:
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Apply OTSU thresholding to get binary representation
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Kernel to dilate horizontally to group letters/words together
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        dilated = cv2.dilate(thresh, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > 20 and h > 10:
                regions.append({
                    "type": "text_region",
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "width": int(w),
                    "height": int(h)
                })
        return regions
    except Exception as e:
        print(f"  [OpenCV] Error finding text regions: {e}")
        return []

def find_windows(image: Image.Image) -> list[dict]:
    """Locates large sub-windows or panels on the screen."""
    try:
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 30, 150)
        
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        windows = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > 200 and h > 150:
                windows.append({
                    "type": "window",
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "width": int(w),
                    "height": int(h)
                })
        return windows
    except Exception as e:
        print(f"  [OpenCV] Error finding windows: {e}")
        return []

def compare_screens(img_a: Image.Image, img_b: Image.Image) -> dict:
    """Compares two images and calculates the percentage of change."""
    try:
        # Resize img_b to match img_a's dimensions if they differ
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size)
            
        cv_a = cv2.cvtColor(np.array(img_a), cv2.COLOR_RGB2BGR)
        cv_b = cv2.cvtColor(np.array(img_b), cv2.COLOR_RGB2BGR)
        
        # Absolute difference
        diff = cv2.absdiff(cv_a, cv_b)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # Threshold difference image
        _, thresh = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
        
        # Calculate percentage of changed pixels
        non_zero = cv2.countNonZero(thresh)
        total_pixels = gray.shape[0] * gray.shape[1]
        change_percent = (non_zero / float(total_pixels)) * 100.0 if total_pixels > 0 else 0.0
        
        # Create a difference image for visualization
        diff_image = Image.fromarray(cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB))
        
        return {
            "changed": change_percent >= 1.0,  # 1% threshold
            "change_percent": float(change_percent),
            "diff_image": diff_image
        }
    except Exception as e:
        print(f"  [OpenCV] Error comparing screens: {e}")
        return {
            "changed": False,
            "change_percent": 0.0,
            "diff_image": img_a
        }
