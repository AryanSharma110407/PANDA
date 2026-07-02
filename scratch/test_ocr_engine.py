import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Enable OCR explicitly
os.environ["DISABLE_OCR"] = "0"

print("Importing ocr_engine...")
try:
    from vision import ocr_engine
    print("[OK] ocr_engine imported successfully.")
except Exception as e:
    print(f"[FAIL] Failed to import ocr_engine: {e}")
    sys.exit(1)

print("\nRunning read_screen()...")
try:
    results = ocr_engine.read_screen()
    print(f"\n[OK] read_screen() completed. Found {len(results)} text regions:")
    for idx, r in enumerate(results[:20]):
        print(f"  {idx+1}. Text: '{r.get('text')}' (Confidence: {r.get('confidence'):.4f}) at BBox: {r.get('bbox')}")
except Exception as e:
    print(f"\n[FAIL] read_screen() crashed with error:")
    import traceback
    traceback.print_exc()
