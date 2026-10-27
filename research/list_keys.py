import re
d = open(r'C:\Users\643\AppData\Local\Temp\opencode\anydesk\anydesk_dump.exe','rb').read()
ks = {}
for m in re.finditer(rb"ad\.[a-z0-9_\.\-]{2,60}", d):
    s = m.group().decode(errors="replace")
    ks.setdefault(s, m.start())
for k, o in sorted(ks.items()):
    print(f"{k:50s} @0x{o:x}")
