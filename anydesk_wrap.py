"""anydesk_wrap.py — IFEO wrapper for AnyDesk.

Hook: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution
Options\AnyDesk.exe\Debugger = "<python> anydesk_wrap.py"

Windows launches the wrapper INSTEAD of AnyDesk.exe for every GUI open and
appends the original command line. This script:

  1. cooldown check (recursion guard; skip reset if last cycle is fresh)
  2. stops the AnyDesk service (recursion re-entry safe: service binary is
     AnyDesk_real.exe, which is IFEO-invisible, so `sc start` flows through it
     normally, bypassing this wrapper)
  3. wipes identity/license keys from programdata confs (all backuped)
  4. restarts the service -> anydesk rebuilds identity and a free license
  5. spawns the real exe so the user gets their window

Note: for SCM-driven starts (--service) we must NOT trigger reset recursions;
SCM passes through to the stock binary directly because the service's
ImagePath was rewritten at install time to the _real.exe copy. This wrapper
is only invoked from interactive launches + UI processes from anydesk itself,
never for SCM service starts.
"""
import os, re, subprocess, sys, time

REAL   = r"C:\Program Files (x86)\AnyDesk\AnyDesk_real.exe"   # IFEO-free copy
DL     = r"C:\ProgramData\AnyDesk"
LOCK   = r"C:\Users\643\.config\openchamber\chats\2026-10-26\session-99c3b3df-2a4c-4cb4-8a5f-a9dc782192a2\anydesk\.reset_lock"
LOG    = r"C:\Users\643\.config\openchamber\chats\2026-10-26\session-99c3b3df-2a4c-4cb4-8a5f-a9dc782192a2\anydesk\wrap.log"
BACKUP = r"C:\Users\643\.config\openchamber\chats\2026-10-26\session-99c3b3df-2a4c-4cb4-8a5f-a9dc782192a2\anydesk\anydesk_keys_backup.json"
COOLDOWN = 12   # seconds; a second open in this window passes through

WIPE_PATTERNS = [
    r"^ad\.license\.", r"^ad\.anynet\.pkey", r"^ad\.anynet\.cert",
    r"^ad\.anynet\.id$", r"^ad\.anynet\.did\.hash", r"^ad\.anynet\.network_hash",
    r"^ad\.anynet\.fpr", r"^ad\.anynet\.client_stats_hash", r"^ad\.inst\.id",
    r"^ad\.ancl\.cached_config", r"^ad\.telemetry\.last_cid",
]

def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%H:%M:%S] ") + msg + "\n")
    except OSError:
        pass

def last_reset():
    try:
        return float(open(LOCK).read())
    except (OSError, ValueError):
        return 0

def reset():
    log("--- new-user cycle ---")
    subprocess.run(["taskkill","/F","/IM","AnyDesk_real.exe"], capture_output=True)
    subprocess.run(["taskkill","/F","/IM","AnyDesk.exe"], capture_output=True)
    subprocess.run(["sc","stop","AnyDesk"], capture_output=True)
    time.sleep(2)

    for fn in ("service.conf", "system.conf"):
        f = os.path.join(DL, fn)
        try:
            lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        keep, gone = [], []
        for ln in lines:
            key = ln.split("=",1)[0].strip()
            if any(re.match(p, key) for p in WIPE_PATTERNS):
                gone.append(ln)
            else:
                keep.append(ln)
        if gone:
            try:
                with open(BACKUP, "a", encoding="utf-8") as b:
                    b.write("### %s %s\n" % (fn, time.strftime("%Y-%m-%d %H:%M:%S")))
                    b.write("\n".join(gone) + "\n")
            except OSError:
                pass
            open(f, "w", encoding="utf-8").write("\n".join(keep) + "\n")
            log(f"{fn}: wiped {len(gone)}")

    subprocess.run(["sc","start","AnyDesk"], capture_output=True)
    time.sleep(4)

def main():
    args = sys.argv[1:]                     # original duplicated cmd line
    log("wrap: " + " ".join(args))
    if time.time() - last_reset() < COOLDOWN:
        log("within cooldown -> pass through")
    else:
        open(LOCK, "w").write(str(time.time()))
        reset()
    if not os.path.isfile(REAL):
        # copy missing (e.g. updater killed it); rebuild before launching
        import shutil
        try:
            shutil.copy2(r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe", REAL)
        except OSError as e:
            log(f"real copy missing: {e}"); return
    subprocess.Popen([REAL] + args)
    log("launched real exe")

if __name__ == "__main__":
    main()
