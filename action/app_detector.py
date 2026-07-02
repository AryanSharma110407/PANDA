"""
PANDA — Desktop Application Detector
======================================
Scans Windows Start Menu shortcuts and Registry to determine if
a specific desktop application is installed locally.
"""

import os
import winreg

def _scan_directory_for_app(directory: str, app_name_lower: str) -> bool:
    """Helper to recursively scan a folder for shortcut (.lnk) or exe files containing app_name."""
    if not os.path.exists(directory):
        return False
        
    for root, dirs, files in os.walk(directory):
        # Check folder names
        for d in dirs:
            if app_name_lower in d.lower():
                return True
        # Check file names (shortcuts or executables)
        for f in files:
            name_lower = f.lower()
            if app_name_lower in name_lower:
                if name_lower.endswith(".lnk") or name_lower.endswith(".exe"):
                    return True
    return False

def _scan_registry_for_app(app_name_lower: str) -> bool:
    """Helper to scan Windows Registry Uninstall keys for the application name."""
    reg_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    ]
    
    for path in reg_paths:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, path) as key:
                    info = winreg.QueryInfoKey(key)
                    for i in range(info[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, f"{path}\\{subkey_name}") as subkey:
                                try:
                                    disp_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    if app_name_lower in disp_name.lower():
                                        return True
                                except OSError:
                                    pass
                        except OSError:
                            pass
            except OSError:
                pass
    return False

def is_app_installed(app_name: str) -> bool:
    """
    Checks if a desktop application is installed locally on the system.
    
    Checks:
      1. User-specific Start Menu shortcuts
      2. System-wide Start Menu shortcuts
      3. Windows Registry Uninstall listings
    """
    app_name_lower = app_name.lower().strip()
    if not app_name_lower:
        return False
        
    # 1. Resolve User and System Start Menu directories
    start_menu_paths = []
    
    # System-wide Programs
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    start_menu_paths.append(os.path.join(program_data, r"Microsoft\Windows\Start Menu\Programs"))
    
    # User-specific Programs
    app_data = os.environ.get("APPDATA")
    if app_data:
        start_menu_paths.append(os.path.join(app_data, r"Microsoft\Windows\Start Menu\Programs"))
        
    for path in start_menu_paths:
        if _scan_directory_for_app(path, app_name_lower):
            return True
            
    # 2. Check Windows Registry
    try:
        if _scan_registry_for_app(app_name_lower):
            return True
    except Exception:
        pass
        
    return False
