#!/usr/bin/env python3
# AnyDesk runtime unpacker / dumper / in-memory patcher
# AnyDesk.exe is packed: tiny .text stub (EP inside), ~30MB virtual .itext,
# 8MB encrypted .data, no import dir. Decryption happens in-process.
# This script: find the running (or freshly started) AnyDesk.exe, wait until
# the image is unpacked in memory (license strings become visible), then:
#   --dump            write anydesk_dump.exe (rva-aligned sections)
#   --find            locate ad.anynet.* string xrefs + loader function + call sites
#   --patch           same, then WriteProcessMemory xor eax,eax;ret onto the loader func
import ctypes, subprocess, time, struct, math, collections, re, sys, os
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
k32.OpenProcess.restype = ctypes.c_void_p

TH32CS_SNAPPROCESS = 0x2

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

def find_pid(name="AnyDesk.exe"):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    e = PROCESSENTRY32W(); e.dwSize = ctypes.sizeof(e)
    k32.Process32FirstW(snap, ctypes.byref(e))
    while True:
        if e.szExeFile.lower() == name.lower():
            k32.CloseHandle(snap)
            return e.th32ProcessID
        if not k32.Process32NextW(snap, ctypes.byref(e)):
            k32.CloseHandle(snap)
            return None

def enable_debug_privilege():
    adv = ctypes.WinDLL("advapi32")
    TOKEN_ADJUST_PRIVILEGES = 0x20; TOKEN_QUERY = 0x8
    htok = ctypes.c_void_p()
    adv.OpenProcessToken(ctypes.WinDLL("kernel32").GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(htok))
    class LUID(ctypes.Structure): _fields_ = [("lo", wintypes.DWORD), ("hi", ctypes.c_long)]
    class TP(ctypes.Structure): _fields_ = [("count", wintypes.DWORD), ("luid", LUID), ("attr", wintypes.DWORD)]
    tp = TP(); tp.count = 1; tp.attr = 2  # SE_PRIVILEGE_ENABLED
    name = ctypes.c_wchar_p("SeDebugPrivilege")
    if not adv.LookupPrivilegeValueW(None, name, ctypes.byref(tp.luid)):
        raise ctypes.WinError(ctypes.get_last_error())
    adv.AdjustTokenPrivileges(htok, False, ctypes.byref(tp), 0, None, None)
    err = ctypes.get_last_error()
    k32.CloseHandle(htok)
    if err == 1300:  # ERROR_NOT_ALL_ASSIGNED
        raise RuntimeError("token does not hold SeDebugPrivilege")
    if err not in (0, 1310):  # 1310 = not all assigned either
        raise ctypes.WinError(err)

def open_proc(pid, ro=False):
    acc = 0x0010 | (0x400 | 0x20 if not ro else 0)   # VM_READ | VM_OPERATION (+ VM_WRITE@0x20)
    h = k32.OpenProcess(acc, False, pid)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    return h

def rpm(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
    return buf.raw[:got.value] if got.value == size else buf.raw

def wpm(h, addr, data):
    wrote = ctypes.c_size_t(0)
    k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(wrote))
    return wrote.value

def module_base_size(h, pid):
    # enumerate modules for a true base (packed image may zero its own headers)
    TH32CS_SNAPMODULE = 0x8
    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlbcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
                    ("modBaseSize", wintypes.DWORD), ("hModule", ctypes.c_void_p),
                    ("szModule", ctypes.c_wchar*256), ("szExePath", ctypes.c_wchar*260)]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    me = MODULEENTRY32W(); me.dwSize = ctypes.sizeof(me)
    ok = k32.Module32FirstW(snap, ctypes.byref(me))
    while ok:
        if me.szModule.lower() == "anydesk.exe":
            k32.CloseHandle(snap)
            return me.modBaseAddr, me.modBaseSize
        ok = k32.Module32NextW(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    return 0x400000, 0x1000000

def read_image_pid(pid):
    h = open_proc(pid)
    base, size = module_base_size(h, pid)
    img = bytearray()
    # chunked read, resume past unreadable gaps
    chunk = 0x100000
    a = base
    end = base + size
    while a < end:
        n = min(chunk, end - a)
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        r = k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got))
        if r and got.value:
            img += buf.raw[:got.value]
        else:
            img += b"\x00" * n
        a += n
    k32.CloseHandle(h)
    return base, size, bytes(img)

def wait_unpacked_dbg(pid, deadline=30):
    h = open_proc(pid, ro=True)
    base, size = module_base_size(h, pid)
    pat = "ad.anynet".encode("utf-16-le")
    t0 = time.time()
    while time.time() - t0 < deadline:
        img = read_image_pid(pid)[2]
        if img and pat in img:
            k32.CloseHandle(h)
            return base, size, img
        time.sleep(0.4)
    base, size, img = read_image_pid(pid)
    k32.CloseHandle(h)
    return base, size, img or None

def read_image(pid):
    h = open_proc(pid, ro=True)
    base, size, _ = module_base_size(h)
    img = rpm(h, base, size)
    k32.CloseHandle(h)
    return base, size, img

# ---------------------------------------------------------------- analysis

def find_strings(img, pat_bytes):
    out, start = [], 0
    while True:
        i = img.find(pat_bytes, start)
        if i < 0: return out
        out.append(i)
        start = i + 2

def find_lea_xrefs(img, img_base, targets, is64=False):
    """scan for lea reg,[rip+disp32] landing on one of targets (rva-file aligned: file off==rva here)"""
    refs = []
    n = len(img)
    for i in range(n - 7):
        # 48/4c 8d 0d|15|05|35... (x64) or 8d 0d|15|05|1d (x86) with byte3 mod=00 rm=101
        b0, b1, b2, b3 = img[i], img[i+1], img[i+2], img[i+3]
        if b1 != 0x8D: continue
        if is64:
            if b0 not in (0x48, 0x4C): continue
        else:
            if b0 & 0xCF: continue     # no rex byte for 32-bit plain lea (accept none)
        if (b2 & 0xC7) != 0x05: continue
        disp = struct.unpack_from("<i", img, i + 3)[0]
        target = (img_base + i + 7) + disp
        if target in targets:
            refs.append((i, target))
    return refs

def find_callees(img, img_base, func_va):
    calls = []
    for i in range(len(img) - 5):
        if img[i] == 0xE8:
            rel = struct.unpack_from("<i", img, i + 1)[0]
            if img_base + i + 5 + rel == func_va:
                calls.append(img_base + i)
    return calls

def find_func_start(img, ref_off):
    """walk back to nearest ret/c3/c2 or int3 padding"""
    j = ref_off
    for back in range(ref_off, max(0, ref_off - 0x3000), -1):
        b = img[back]
        if b in (0xC3, 0xC2):          # ret is typical function end/start boundary
            return back + 1
        if b == 0xCC and img[back+1:back+1+4] != b"\xcc\xcc\xcc\xcc":
            continue
    return None

# ---------------------------------------------------------------- dump

def make_dump(img, base):
    d = bytearray(img)
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e+6)[0]
    opt = e + 24
    so = opt + struct.unpack_from("<H", d, e+20)[0]
    for i in range(n):
        o = so + i*40
        name, vsz, va, rs, ro = struct.unpack_from("<8sIIII", d, o)
        # rva-aligned layout: raw off = va, raw size = vsize
        struct.pack_into("<II", d, o+12, vsz, va)
    old_ep = struct.unpack_from("<I", d, opt+16)[0]
    struct.pack_into("<I", d, opt+16, old_ep)   # keep packer EP; analysis dump
    return bytes(d)

# ---------------------------------------------------------------- main

def main():
    exe = r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe"
    dump  = "--dump"  in sys.argv
    do_p  = "--patch" in sys.argv
    find  = "--find"  in sys.argv
    start = "--start" in sys.argv

    pid = find_pid()
    if start and not pid:
        print("[*] launching AnyDesk.exe")
        subprocess.Popen([exe], creationflags=0x00000008 | 0x00000200)  # DETACHED|NEW_JOB? keep simple
        for _ in range(60):
            time.sleep(0.5); pid = find_pid()
            if pid: break
        if not pid: print("!! no pid"); return 1
    if not pid:
        print("!! AnyDesk.exe not running; use --start"); return 1
    print(f"[*] pid {pid}")
    try:
        enable_debug_privilege()
        print("[*] SeDebugPrivilege on")
    except Exception as ex:
        print(f"[!] SeDebugPrivilege: {ex}")
    # sanity: can we open another protected-ish system proc?
    import subprocess as sp
    pids = [int(x) for x in sp.run(["tasklist","/fi","IMAGENAME eq lsass.exe","/fo","csv","/nh"],capture_output=True,text=True).stdout.split(b'"' * 1)[0].strip().strip('"').split(",")[1].strip('"')] if False else None
    lsass = sp.run(["powershell","-c","(Get-Process lsass).Id"],capture_output=True,text=True).stdout.strip()
    if lsass.isdigit():
        try:
            h2 = open_proc(int(lsass), ro=True); k32.CloseHandle(h2)
            print("[*] sanity: lsass open OK")
        except OSError as e:
            print(f"[*] sanity: lsass DENIED ({e}) -> token issue, not AnyDesk")
    who = sp.run(["powershell","-c","(Get-Process -Id %d).StartInfo.UserName" % pid],capture_output=True,text=True).stdout.strip()
    owner = sp.run(["powershell","-c","(Get-CimInstance Win32_Process -Filter \"ProcessId=%d\" | Invoke-CimMethod -MethodName GetOwner).User" % pid],capture_output=True,text=True).stdout.strip()
    domain = sp.run(["powershell","-c","$o=(Get-CimInstance Win32_Process -Filter \"ProcessId=%d\" | Invoke-CimMethod -MethodName GetOwner); \"$($o.Domain)\\$($o.User)\"" % pid],capture_output=True,text=True).stdout.strip()
    print(f"[*] AnyDesk pid {pid} owner: {domain}")

    base, size, img = wait_unpacked_dbg(pid, 30)
    if img is None:
        print("[*] strings wait timed out - reading image anyway")
        base, size, img = read_image(pid)
    print(f"[*] base 0x{base:x} size 0x{size:x} img {len(img)} / {size}")

    targets = {}
    for s in ("ad.anynet.user_token", "ad.license", "customer.expiry", "ad.features"):
        hits = find_strings(img, s.encode("utf-16-le"))
        print(f"[*] utf16 '{s}' x{len(hits)} {['0x%x'%h for h in hits[:8]]}")
        for h in hits: targets[base + h] = s
    if not targets:
        print("[*] not in module image -> scanning ALL committed memory")
        target_all = read_image_pid(pid)[2]
        for s in ("ad.anynet.user_token", "ad.license"):
            hs = find_strings(target_all, s.encode("utf-16-le"))
            print(f"[*] whole-mem '{s}' x{len(hs)} {['0x%x'%h for h in hs[:8]]}")
        hs2 = find_strings(target_all, b"AnyDesk")
        print("[*] 'AnyDesk' ansi x%d" % len(hs2))

    refs = find_lea_xrefs(img, base, set(targets))
    print(f"[*] {len(refs)} lea refs to license strings:")
    for off, tgt in refs:
        fs = find_func_start(img, off)
        print(f"    ref img_off 0x{off:x} (va 0x{base+off:x})  ->  '{targets[tgt]}'  func_start ~ 0x{(fs if fs is not None else 0):x}")

    if dump:
        data = make_dump(img, base)
        out = r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\anydesk_dump.exe"
        open(out, "wb").write(data)
        print(f"[*] dump written {out} ({len(data)} bytes)")

    if do_p:
        h = open_proc(pid)
        patched = 0
        for off, tgt in refs:
            fs = find_func_start(img, off)
            if fs is None: continue
            va = base + fs
            stub = b"\x31\xC0\xC3"          # xor eax,eax ; ret
            w = wpm(h, va, stub)
            if w == len(stub):
                patched += 1
                print(f"[+] patched func @ va 0x{va:x} ({targets[tgt]} path)")
        k32.CloseHandle(h)
        print(f"[+] {patched} functions patched in-memory; anydesk now lives fresh-user flow")

if __name__ == "__main__":
    class _Tee:
        def __init__(self, *f): self.f = f
        def write(self, s):
            for x in self.f: x.write(s); x.flush()
        def flush(self):
            for x in self.f: x.flush()
    import io
    logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anydesk_rt.log")
    sys.stdout = _Tee(sys.stdout, open(logpath, "w", encoding="utf-8", buffering=1))
    sys.stderr = sys.stdout
    sys.exit(main())
