import urllib.request
from pathlib import Path
import tarfile 

INSTALL = Path.home() / ".eaphammer/"

if not INSTALL.exists():
    INSTALL.mkdir(parents=True)

packages = [("binutils", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/binutils-2.39-r2.apk"),
("gcc", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/gcc-12.2.1_git20220924-r4.apk"),
("g++", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/g%2B%2B-12.2.1_git20220924-r4.apk"),
("libc", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/libc-dev-0.7.2-r3.apk"),
("libc-dev", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/libc-dev-0.7.2-r4.apk"),
("fortify-headers", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/fortify-headers-1.1-r1.apk"),
("musl", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/musl-1.2.3-r4.apk"),
("musl-dev", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/musl-dev-1.2.3-r4.apk"),
("zlib", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/zlib-1.2.13-r0.apk"),
("zlib-dev", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/zlib-dev-1.2.13-r0.apk"),
("openssl", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/openssl-3.0.8-r0.apk"),
("openssl-dev", "https://dl-cdn.alpinelinux.org/alpine/v3.17/main/aarch64/openssl-dev-3.0.8-r0.apk"),
("libgcrypt", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/libgcrypt-1.10.1-r1.apk"),
("libgcrypt-dev", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/libgcrypt-dev-1.10.1-r1.apk"),
("libcurl", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/libcurl-7.88.1-r1.apk"),
("curl-dev", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/curl-dev-7.88.1-r1.apk"),
("ncurses", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/libncursesw-6.4_p20230225-r0.apk"),
("readline", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/readline-8.2.1-r0.apk"),
("bash", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/bash-5.2.15-r0.apk"),
("musl-utils", "https://dl-cdn.alpinelinux.org/alpine/edge/main/aarch64/musl-utils-1.2.3-r4.apk")]
def install(pkg):
    with tarfile.open(pkg, "r:gz") as tar:
        for entry in tar.getmembers():
            tar.extract(entry, INSTALL)
    pkg.unlink()

[(urllib.request.urlretrieve(y, "/tmp/{}.apk".format(x)) and (lambda z: install(Path(z)))("/tmp/{}.apk".format(x))) for x, y in packages]
