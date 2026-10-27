#!/usr/bin/env python3
"""
anydesk_watch.py - SYSTEM watchdog: whenever AnyDesk opens, give it a new user.

Runs forever (ONSTART scheduled task). Loop:
  1. wait for anydesk.exe to appear
  2. kill it, stop service
  3. wipe license/identity keys from ProgramData configs (backup kept)
  4. start service (reads empty conf -> generates brand-new ID + license)
  5. relaunch the GUI so the operator sees the fresh session
  6. cooldown 30s, repeat

Output -> anydesk_watch.log (append).
"""
import os, re, subprocess, sys, time

DL        = r"C:\ProgramData\AnyDesk"
EXE       = r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe"
LOG       = r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\anydesk_watch.log"
BACKUP    = r"C:\Users\643\AppData\Local\Temp\opencode\anydesk\anydesk_keys_backup.json"
COOLDOWN  = 30
POLL      = 2

WIPE_PATTERNS = [
    r"^ad\.license\.", r"^ad\.anynet\.pkey", r"^ad\.anynet\.cert",
    r"^ad\.anynet\.id$", r"^ad\.anynet\.did\.hash", r"^ad\.anynet\.network_hash",
    r"^ad\.anynet\.fpr", r"^ad\.anynet\.client_stats_hash", r"^ad\.inst\.id",
    r"^ad\.ancl\.cached_config", r"^ad\.telemetry\.last_cid",
]

def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except OSError:
        pass

def pids(name="AnyDesk.exe"):
    out = subprocess.run(["tasklist","/FI","IMAGENAME eq %s" % name,"/FO","CSV","/NH"],
                         capture_output=True, text=True).stdout
    return [int(l.split(",")[1].strip('"')) for l in out.splitlines() if l.strip().startswith('"')]

def kill_all():
    subprocess.run(["taskkill","/F","/IM","AnyDesk.exe"], capture_output=True)
    time.sleep(1)

def svc(action="stop"):
    subprocess.run(["sc", action, "AnyDesk"], capture_output=True)

def wipe():
    for fn in ("service.conf", "system.conf"):
        f = os.path.join(DL, fn)
        if not os.path.isfile(f):
            continue
        lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        keep, gone = [], []
        for ln in lines:
            key = ln.split("=",1)[0].strip()
            (gone if any(re.match(p, key) for p in WIPE_PATTERNS) else keep).append(ln)
        if gone:
            try:
                with open(BACKUP, "a", encoding="utf-8") as b:
                    b.write("### %s %s\n" % (fn, time.strftime("%Y-%m-%d %H:%M:%S")))
                    b.write("\n".join(gone) + "\n")
            except OSError:
                pass
            open(f, "w", encoding="utf-8").write("\n".join(keep) + "\n")
            log("%s: wiped %d keys" % (fn, len(gone)))
        else:
            log("%s: already clean" % fn)

def new_id():
    try:
        c = open(os.path.join(DL,"service.conf"), encoding="utf-8").read()
        m = re.search(r"^ad\.anynet\.id=(\d+)", c, re.M)
        return m.group(1) if m else "(pending)"
    except OSError:
        return "?"

def reset_once():
    log("--- reset cycle ---")
    kill_all()
    svc("stop"); time.sleep(2)
    wipe()
    svc("start")
    time.sleep(5)
    log("new id: " + new_id())
    # relaunch the launcher so the operator gets their window back
    try:
        subprocess.Popen([EXE])
    except OSError as e:
        log("relaunch: " + str(e))

def main():
    log("watchdog started (pid %d)" % os.getpid())
    cooldown_until = 0
    while True:
        now = time.time()
        seen = pids()
        if seen and now >= cooldown_until:
            log("anydesk opened (pids %s) -> resetting" % seen)
            reset_once()
            cooldown_until = time.time() + COOLDOWN
        time.sleep(POLL)

if __name__ == "__main__":
    main()
