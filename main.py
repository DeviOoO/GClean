import ctypes
import sys
import os

SW_SHOWNORMAL = 1
SW_HIDE = 0
is_admin = ctypes.windll.shell32.IsUserAnAdmin()


if not is_admin:
    script = os.path.abspath(sys.argv[0])
    params = f'"{script}"'
    
    
    ctypes.windll.shell32.ShellExecuteW(
    None,            # Parent window handle (None/NULL)
    "runas",         # Verb: "runas" for Admin, "open" for standard launch
    sys.executable,  # Path to the executable (e.g., python.exe)
    params,     # Parameters to pass
    None,            # Working directory (None uses current)
    SW_HIDE    # How to show the window
)
    sys.exit()
    
if is_admin:
    from ui.interface import InterfaceRoot