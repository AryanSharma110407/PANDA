import sys
sys.path.insert(0, '.')
print('Testing vision layer imports...')

from vision import ui_automation_engine
print('  [OK] ui_automation_engine')

from vision import element_registry
print('  [OK] element_registry')

from vision import screen_state
print('  [OK] screen_state')

from vision.vision_tools import handle_look, handle_look_text, handle_find, handle_describe_screen
print('  [OK] vision_tools')

print()
print('Testing Layer 1 availability...')
avail = ui_automation_engine.is_available()
print(f'  UI Automation available: {avail}')

if avail:
    wins = ui_automation_engine.list_windows()
    print(f'  Visible windows: {len(wins)}')
    for w in wins[:5]:
        title = w.get("title", "?")
        print(f'    - {title}')

print()
print('All checks passed.')
