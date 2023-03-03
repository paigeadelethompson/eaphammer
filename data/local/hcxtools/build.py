from SCons.Environment import Environment
from pathlib import Path


INSTALL = Path.home() / ".eaphammer/"

if not INSTALL.exists():
    INSTALL.mkdir(parents=True)

files_link = {
    "hcxpcaptool.c":
    ("z", "crypto"),
    "hcxpsktool.c":
    ("crypto",),
    "hcxhashcattool.c":
    ("crypto", "pthread"),
    "wlanhc2hcx.c": (),
    "wlanwkp2hcx.c": (),
    "wlanhcxinfo.c": (),
    "wlanhcx2cap.c":
    ("pcap",),
    "wlanhcx2essid.c": (),
    "wlanhcx2ssid.c": (),
    "wlanhcxmnc.c": (),
    "wlanhashhcx.c": (),
    "wlanhcxcat.c":
    ("crypto",),
    "wlanpmk2hcx.c":
    ("crypto",),
    "wlanjohn2hcx.c": (),
    "wlancow2hcxpmk.c": (),
    "whoismac.c":
    ("curl",),
    "wlanhcx2john.c": (),
    "wlanhcx2psk.c":
    ("crypto",),
    "wlancap2wpasec.c":
    ("curl",)
}

files_ccflags = {
    "hcxpcaptool.c":
    ("-std=c99",),
    "hcxpsktool.c":
    ("-std=c99",),
    "hcxhashcattool.c":
    ("-std=c99",),
    "wlanhc2hcx.c": ("-std=c99",),
    "wlanwkp2hcx.c": ("-std=c99",),
    "wlanhcxinfo.c": ("-std=c99",),
    "wlanhcx2cap.c":
    ("-std=c99",),
    "wlanhcx2essid.c": ("-std=c99",),
    "wlanhcx2ssid.c": ("-std=c99",),
    "wlanhcxmnc.c": ("-std=c99",),
    "wlanhashhcx.c": ("-std=c99",),
    "wlanhcxcat.c":
    ("-std=c99",),
    "wlanpmk2hcx.c":
    ("-std=c99",),
    "wlanjohn2hcx.c": ("-std=c99",),
    "wlancow2hcxpmk.c": ("-std=c99",),
    "whoismac.c":
    ("-std=c99",),
    "wlanhcx2john.c": ("-std=c99",),
    "wlanhcx2psk.c":
    ("-std=c99",),
    "wlancap2wpasec.c":
    ("-std=c99",)
}

[Environment(CCFLAGS=files_ccflags.get(x)).Object(x).pop().build() for x in files_ccflags.keys()]
[Environment().Program(target=x.replace(".c", ""), source=x.replace(".c", ".o"),
                       LIBS=files_link.get(x)).pop().build() for x in files_link.keys()]

# XXX install
