# PANDA Vision — Templates Directory

This directory previously stored hardcoded `.png` template images for
OpenCV template matching (`find_image_on_screen`). That approach has been
**replaced** by the dynamic 3-layer vision stack.

## New Architecture

```
Layer 1 (Primary)  → Windows UI Automation (uiautomation library)
                     Finds elements by their accessible name — no images needed.

Layer 2 (Fallback) → PaddleOCR
                     Reads all text on screen, fuzzy-matches your query.

Layer 3            → OpenCV
                     Used only for change detection (compare_screens).
                     NOT used for element finding anymore.
```

## This folder is now unused for element finding.

Template matching via OpenCV is unreliable because:
- Images break when the icon moves, resizes, or changes with theme
- Requires manually screenshotting every element you want to find
- Fails completely if the template file is missing

The new dynamic discovery system requires **zero setup** — just say
`"find the Submit button"` and PANDA searches the live accessibility tree.
