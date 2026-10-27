#!/usr/bin/env python3
"""
new_user.py - AnyDesk "always new user" config patcher

Strategy: license token cache + identity lives entirely in config.
  ad.license.state_store / name / expiry  -> cached license state
  ad.anynet.pkey / cert                   -> client identity keypair
  ad.inst.id / ad.anynet.id               -> AnyDesk ID
Wipe them, restart the service -> AnyDesk regenerates identity + license
freshly at every start. Default mode ad-hoc.

Modes:
  python new_user.py              # one shot: stop, wipe keys, start
  python new_user.py --install    # + register ONSTART SYSTEM task, so every boot/reset is fresh

backup of removed keys -> <folder>\anydesk_keys_backup.json
"""
import ctypes, json, os, re, shutil, subprocess, sys, time

DL = r"C:\ProgramData\AnyDesk"
BACKUP = r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\anydesk_keys_backup.json"

WIPE_PATTERNS = [
    r"^ad\.license\.",                 # state_store, name, expiry, whatever
    r"^ad\.anynet\.pkey",              # identity keypair
    r"^ad\.anynet\.cert",
    r"^ad\.anynet\.id$",               # AnyDesk ID
    r"^ad\.anynet\.did\.hash",
    r"^ad\.anynet\.network_hash",
    r"^ad\.anynet\.fpr",
    r"^ad\.anynet\.client_stats_hash",
    r"^ad\.inst\.id",
    r"^ad\.ancl\.cached_config",       # cached cloud config, may pin license
    r"^ad\.telemetry\.last_cid",
]

def log(m):
    try:
        with open(r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\new_user_run.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + m + "\n")
    except OSError:
        print(m, flush=True)

def svc(action="stop"):
    subprocess.run(["sc", action, "AnyDesk"], capture_output=True)

def kill_gui():
    subprocess.run(["taskkill", "/F", "/IM", "AnyDesk.exe"], capture_output=True)

def wipe():
    # cooldown: skip if a reset happened in the last 30s (WMI can fire multiple times)
    LOCK = r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\.reset_lock"
    try:
        t = float(open(LOCK).read())
        if time.time() - t < 30:
            return
    except (OSError, ValueError):
        pass
    open(LOCK, "w").write(str(time.time()))
    for f in (os.path.join(DL,"service.conf"), os.path.join(DL,"system.conf")):
        if not os.path.isfile(f): continue
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        kept, removed = [], []
        for ln in lines:
            key = ln.split("=",1)[0].strip()
            if any(re.match(p, key) for p in WIPE_PATTERNS):
                removed.append(ln)
            else:
                kept.append(ln)
        if removed:
            with open(BACKUP, "a", encoding="utf-8") as b:
                b.write("### %s %s\n" % (f, time.strftime("%Y-%m-%d %H:%M:%S")))
                b.write("\n".join(removed) + "\n")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("\n".join(kept) + "\n")
            log("[%s] removed %d keys" % (os.path.basename(f), len(removed)))
            for r in removed:
                log("   - " + r.split("=")[0] + "=" + r.split("=",1)[1][:40])
        else:
            log("[%s] nothing to remove" % os.path.basename(f))

def regen_restart():
    svc("start")
    time.sleep(4)
    out = subprocess.run(["sc","query","AnyDesk"], capture_output=True, text=True).stdout
    log("[*] service state: " + ("RUNNING" if "RUNNING" in out else "not running"))
    # show new identity
    try:
        conf = open(os.path.join(DL,"service.conf"),"r").read()
        m = re.search(r"^ad\.anynet\.id=(\d+)", conf, re.M)
        log("[*] new ad.anynet.id: " + (m.group(1) if m else "(generating)"))
    except Exception as e:
        log("   " + str(e))

def install_task():
    cmd = r"python C:\Users\643\AppData\Local\Temp\opencode\anydesk\new_user.py"
    subprocess.run(["schtasks","/Create","/TN","AnyDeskNewUser","/SC","ONSTART",
                    "/RU","SYSTEM","/RL","HIGHEST","/TR",cmd], capture_output=True)
    r = subprocess.run(["schtasks","/Query","/TN","AnyDeskNewUser"], capture_output=True, text=True).stdout
    log("[*] task AnyDeskNewUser: " + ("registered" if "AnyDeskNewUser" in r else "FAILED"))

if __name__ == "__main__":
    # Elevated/SYSTEM check not needed: the system runs it as SYSTEM via schtasks
    log("[*] killing anydesk ui + stopping service")
    kill_gui()
    svc("stop")
    time.sleep(2)
    wipe()
    if "--install" in sys.argv:
        install_task()
    regen_restart()
    log("[*] done - fresh license, fresh id, fresh user")
