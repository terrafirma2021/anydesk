import ctypes, subprocess, sys
from ctypes import wintypes
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32")

# privilege state
class LUID(ctypes.Structure): _fields_=[("lo",wintypes.DWORD),("hi",ctypes.c_long)]
class TP(ctypes.Structure): _fields_=[("count",wintypes.DWORD),("luid",LUID),("attr",wintypes.DWORD)]
htok=ctypes.c_void_p(); adv.OpenProcessToken(k32.GetCurrentProcess(),0x28,ctypes.byref(htok))
tok=ctypes.c_ulong(); adv.GetTokenInformation(htok,20,ctypes.byref(tok),4,None)  # TokenElevation
print("elevated:",tok.value)
tp=TP(); tp.count=1; tp.attr=2
adv.LookupPrivilegeValueW(None,"SeDebugPrivilege",ctypes.byref(tp.luid))
adv.AdjustTokenPrivileges(htok,False,ctypes.byref(tp),0,None,None)
print("adjust err:",ctypes.get_last_error())

def t(pid,label):
    h=k32.OpenProcess(0x10|0x20|0x400|0x1,False,pid)
    print(label,pid,"ok" if h else ("DENIED err %d"%ctypes.get_last_error()))
    if h:k32.CloseHandle(h)

# own
notepad=subprocess.Popen("notepad"); t(notepad.pid,"notepad(user)")
own=k32.GetCurrentProcessId(); t(own,"self")
for nm in ("services.exe","AnyDesk.exe","explorer.exe"):
    out=subprocess.run(["powershell","-c","(Get-Process %s -ErrorAction SilentlyContinue | Select -First 1).Id"%nm],capture_output=True,text=True).stdout.strip()
    if out.isdigit(): t(int(out),nm)
notepad.kill()
