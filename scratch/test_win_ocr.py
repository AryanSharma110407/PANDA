import sys
import os
import subprocess
import json
import time
# pyrefly: ignore [missing-import]
from PIL import Image

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision.screenshot_manager import capture_screen

def test_native_win_ocr():
    print("Capturing screen...")
    img = capture_screen()
    
    # Save to temp file
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, "ocr_temp.png")
    img.save(temp_path)
    print(f"Saved temp screenshot to: {temp_path}")
    
    # PowerShell script to run Windows.Media.Ocr
    ps_script = f"""
    [Void][ObjRefs]
    try {{
        $assembly1 = [System.Reflection.Assembly]::LoadWithPartialName("System.Runtime.WindowsRuntime")
        
        # Load WinRT Types
        $OcrEngineType = [Type]::GetType("Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime")
        $BitmapDecoderType = [Type]::GetType("Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime")
        $StorageFileType = [Type]::GetType("Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime")
        
        if (-not $OcrEngineType) {{
            Write-Error "Windows OCR API is not available on this system."
            exit 1
        }}

        $imgPath = "{temp_path}"
        $fileTask = [Windows.Storage.StorageFile]::GetFileFromPathAsync($imgPath)
        while (-not $fileTask.IsCompleted) {{ Start-Sleep -Milliseconds 10 }}
        $file = $fileTask.GetResults()

        $streamTask = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
        while (-not $streamTask.IsCompleted) {{ Start-Sleep -Milliseconds 10 }}
        $stream = $streamTask.GetResults()

        $decoderTask = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
        while (-not $decoderTask.IsCompleted) {{ Start-Sleep -Milliseconds 10 }}
        $decoder = $decoderTask.GetResults()

        $bitmapTask = $decoder.GetSoftwareBitmapAsync()
        while (-not $bitmapTask.IsCompleted) {{ Start-Sleep -Milliseconds 10 }}
        $bitmap = $bitmapTask.GetResults()

        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        $ocrTask = $engine.RecognizeAsync($bitmap)
        while (-not $ocrTask.IsCompleted) {{ Start-Sleep -Milliseconds 10 }}
        $ocrResult = $ocrTask.GetResults()

        $words = @()
        foreach ($line in $ocrResult.Lines) {{
            foreach ($word in $line.Words) {{
                $rect = $word.Rect
                $words += @{{
                    text = $word.Text
                    x = $rect.X
                    y = $rect.Y
                    width = $rect.Width
                    height = $rect.Height
                }}
            }}
        }}
        $words | ConvertTo-Json -Compress
    }} catch {{
        Write-Error $_.Exception.Message
        exit 1
    }}
    """
    
    print("Running PowerShell native OCR...")
    start_time = time.time()
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            check=True
        )
        duration = time.time() - start_time
        print(f"OCR finished in {duration:.4f} seconds.")
        
        output = proc.stdout.strip()
        if not output:
            print("OCR returned empty output.")
            return
            
        words = json.loads(output)
        print(f"Found {len(words)} words:")
        # Print top 15 words
        for idx, w in enumerate(words[:15]):
            print(f"  - '{w['text']}' at ({w['x']:.1f}, {w['y']:.1f}, {w['width']:.1f}, {w['height']:.1f})")
            
    except subprocess.CalledProcessError as e:
        print(f"PowerShell OCR failed: {e}")
        print(f"Stderr: {e.stderr}")
    except Exception as e:
        print(f"Error parsing OCR output: {e}")
        
if __name__ == "__main__":
    test_native_win_ocr()
