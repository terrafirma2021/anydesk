import ctypes, sys
from ctypes import wintypes
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32")
log = open(r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\probe2.log", "w")
def p(*a): print(*a); print(*a, file=log); log.flush()

class LUID(ctypes.Structure): _fields_=[("lo",wintypes.DWORD),("hi",ctypes.c_long)]
class TP(ctypes.Structure): _fields_=[("count",wintypes.DWORD),("luid",LUID),("attr",wintypes.DWORD)]
htok=ctypes.c_void_p()
r=adv.OpenProcessToken(k32.GetCurrentProcess(),0x28,ctypes.byref(htok))
ele=ctypes.c_ulong(); rl=ctypes.c_ulong()
r2=adv.GetTokenInformation(htok,20,ctypes.byref(ele),4,ctypes.byref(rl))
p("isadmin-query-ok",r,"elevated:",ele.value if r2 else "err%d"%ctypes.get_last_error())
tp=TP(); tp.count=1; tp.attr=2
adv.LookupPrivilegeValueW(None,"SeDebugPrivilege",ctypes.byref(tp.luid))
adv.AdjustTokenPrivileges(htok,False,ctypes.byref(tp),0,None,None)
p("adjust err:",ctypes.get_last_error())
# read back privilege state
z=ctypes.c_ulong(0); pvs=ctypes.c_ulong(0)
adv.GetTokenInformation(htok,16,None,0,ctypes.byref(pvs))   # TokenPrivileges
buf=ctypes.create_string_buffer(pvs.value)
adv.GetTokenInformation(htok,16,buf,pvs.value,ctypes.byref(pvs))
cnt=ctypes.cast(buf,ctypes.POINTER(ctypes.c_ulong)).contents.value
import struct as st
o=4
for _ in range(cnt):
    luid, attr = st.unpack_from("<IQ", buf, o)
    nm=ctypes.create_unicode_buffer(64); nl=ctypes.c_ulong(64)
    adv.LookupPrivilegeNameW(None, luid, nm, ctypes.byref(nl))
    if "Debug" in nm.value: p("priv:",nm.value,"attr=0x%x"%attr)
    o += 12
def t(pid,label,acc=0x431):
    h=k32.OpenProcess(acc,False,pid)
    p(label,pid,"OPEN ok" if h else ("DENIED err %d"%ctypes.get_last_error()))
    if h:k32.CloseHandle(h)

t(1404,"services(SYSTEM/PPL)")
t(32376,"AnyDesk(SYSTEM)")
t(34984,"notepad")
t(k32.GetCurrentProcessId(),"self")
t(4,"System")
