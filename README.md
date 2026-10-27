# anydesk

Turns AnyDesk into a fresh free license every time it is opened. Fully
automatic, no resident process, no polling, no manual steps.

## How it works

The AnyDesk service (SYSTEM) keeps its identity and license state entirely in
`t::::::C:\ProgramData\AnyDesk\service.conf` / `system.conf`:

Key roles that matter:

Key | Part of
ad.license.state_store / name / expiry | cached license token
ad.anynet.pkey + cert | client identity key pair (license is bound here)
ad.inst.id / ad.anynet.id | the AnyDesk ID itself
ad.anynet.did.hash / fpr / client_stats_hash | identity hashes

The chain:

    user opens AnyDesk.exe
        -> Windows IFEO hook fires (Image File Execution Options)
        -> python anydesk_wrap.py <original args>
        -> stop service
        -> wipe identity and license keys from both confs (backup kept)
        -> start service
        -> service sees no identity -> generates fresh keypair + cert + free license
        -> wrapper launches real exe so the GUI appears
        -> brand new user, brand new ID, every single open

The service binary itself is redirected to `AnyDesk_real.exe` (a plain copy of
AnyDesk.exe, made by `install.ps1`) so Windows never trips the IFEO hook when
the SCM starts the service. Only GUI opens go through the wrapper.

No exe files are patched at all. The behavior comes from AnyDesk's own
reaction to an empty config.

## Install

1. Open an elevated the PowerShell prompt once.

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install` does:

1. Copy `AnyDesk.exe` next to the original under and name it `AnyDesk_real.exe`.
2. Reset the service ImagePath registry value to `AnyDesk_real.exe --service`.
3. Add the IFEO Debug key for `AnyDesk.exe` pointing at `anydesk_wrap.py`.
4. Start the service and print the freshly generated ID.

That's it. Windows now interrupts every future open and feeds them the
wrapper.

## Uninstall

See `uninstall.ps1`: removes the IFEO key, points the service back at
`AnyDesk.exe --service`, and deletes the copy of the exe. Configs are left as
they are (the next AnyDesk start builds a fresh identity from whatever the
wrapper last produced; delete the keys if you want a brand new one anyway).

## Files

File | role
anydesk_wrap.py | the wrapper Windows calls instead of AnyDesk.exe
install.ps1 / uninstall.ps1 | one-time elevated setup and teardown, idempotent
anydesk_keys_backup.json | append-only record of every wiped key set
wmi_setup.ps1 / anydesk_sub.mof | older WMI approach, kept for reference, **not** part of the flow
anydesk_watch.py | older polling watchdog, kept for reference
new_user.py | one-shot reset and restart, kept for reference

Log locations (wraplog): `wrap.log` gets appended on every open.
new_user_run.log stays where the reset script path would put it.

The `dump` and runtime analysis scripts for the binary (packed with custom
packer, .itext is huge and raw-empty, EP is inside tiny .text) live in the
`research` folder but they are not part of the working install path.

## Notes

* Tested on Windows 11 x64, AnyDesk 9.x installed under `C:\Program Files (x86)\AnyDesk` running as service.
* AnyDesk updater replaces `AnyDesk.exe`. `install.ps1` handles this by re-copying `AnyDesk_real.exe`.
* Config location and paths assume the default install.
* ~10 second delay per open: the reset needs the service restart cycle.
