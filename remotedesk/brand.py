#!/usr/bin/env python3
"""RemoteDesk branding for the RustDesk fork (run in CI after checkout).

Env vars:
  RD_APP_NAME  product name, no spaces (default: RemoteDesk)
  RD_SERVER    rendezvous server host (optional; without it the build keeps
               RustDesk's public servers and prints a warning)
  RD_KEY       server public key (required if RD_SERVER is set)

Fails loudly if any patch target is missing, so an upstream change can never
silently produce an unbranded build.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = os.environ.get("RD_APP_NAME", "").strip() or "RemoteDesk"
SERVER = os.environ.get("RD_SERVER", "").strip()
KEY = os.environ.get("RD_KEY", "").strip()


def die(msg: str) -> None:
    print(f"::error::{msg}")
    sys.exit(1)


def sub_once(path: Path, pattern: str, repl: str) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        die(f"patch target not found in {path}: {pattern}")
    path.write_text(new, encoding="utf-8")
    print(f"patched {path.relative_to(ROOT)}: {pattern}")


if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,30}", NAME):
    die("RD_APP_NAME must be 3-31 letters/digits, no spaces")
if SERVER and not KEY:
    die("RD_KEY is required when RD_SERVER is set")
if SERVER and not re.fullmatch(r"[A-Za-z0-9.-]+(:\d+)?", SERVER):
    die("RD_SERVER must be a host name or IP, without http://")
if KEY and not re.fullmatch(r"[A-Za-z0-9+/=]{40,60}", KEY):
    die("RD_KEY does not look like a base64 ed25519 public key")

# 1) Core config: app name (makes it a "custom client": no RustDesk update
#    prompts), our server and its public key.
cfg = ROOT / "libs/hbb_common/src/config.rs"
sub_once(cfg, r'(APP_NAME: RwLock<String> = RwLock::new\()"RustDesk"', rf'\1"{NAME}"')
if SERVER:
    sub_once(cfg, r'^pub const RENDEZVOUS_SERVERS: &\[&str\] = &\[.*?\];',
             f'pub const RENDEZVOUS_SERVERS: &[&str] = &["{SERVER}"];')
    sub_once(cfg, r'^pub const RS_PUB_KEY: &str = ".*?";',
             f'pub const RS_PUB_KEY: &str = "{KEY}";')
else:
    print("::warning::RD_SERVER not set: this build uses RustDesk public servers")

# 2) Windows version resource strings.
rc = ROOT / "flutter/windows/runner/Runner.rc"
sub_once(rc, r'"FileDescription", "RustDesk Remote Desktop"', f'"FileDescription", "{NAME}"')
sub_once(rc, r'"ProductName", "RustDesk"', f'"ProductName", "{NAME}"')
sub_once(rc, r'"OriginalFilename", "rustdesk.exe"', f'"OriginalFilename", "{NAME}.exe"')

# Version resources of librustdesk.dll and of the portable packer (outer .exe).
for toml in ["Cargo.toml", "libs/portable/Cargo.toml"]:
    p = ROOT / toml
    sub_once(p, r'^ProductName = "RustDesk"$', f'ProductName = "{NAME}"')
    sub_once(p, r'^FileDescription = "RustDesk Remote Desktop"$', f'FileDescription = "{NAME}"')
    sub_once(p, r'^OriginalFilename = "rustdesk.exe"$', f'OriginalFilename = "{NAME}.exe"')

# 2b) UI accent color (buttons, links, highlights).
ACCENT = os.environ.get("RD_ACCENT", "").strip() or "0891B2"
if not re.fullmatch(r"[0-9A-Fa-f]{6}", ACCENT):
    die("RD_ACCENT must be a 6-digit hex color")
dart = ROOT / "flutter/lib/common.dart"
sub_once(dart, r"static const Color accent = Color\(0xFF0071FF\);", f"static const Color accent = Color(0xFF{ACCENT});")
sub_once(dart, r"static const Color accent50 = Color\(0x770071FF\);", f"static const Color accent50 = Color(0x77{ACCENT});")
sub_once(dart, r"static const Color accent80 = Color\(0xAA0071FF\);", f"static const Color accent80 = Color(0xAA{ACCENT});")

# 3) Icons: use remotedesk/icon.png if present, otherwise draw a provisional one.
from PIL import Image, ImageDraw  # noqa: E402  (pip install pillow in CI)

src = ROOT / "remotedesk/icon.png"
if src.exists():
    base = Image.open(src).convert("RGBA").resize((512, 512), Image.LANCZOS)
else:
    s = 512
    base = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([16, 16, s - 16, s - 16], radius=110, fill=(37, 99, 235, 255))
    d.rounded_rectangle([104, 128, 408, 330], radius=26, outline=(255, 255, 255, 255), width=30)
    d.rectangle([236, 330, 276, 380], fill=(255, 255, 255, 255))
    d.rounded_rectangle([176, 372, 336, 400], radius=14, fill=(255, 255, 255, 255))
    d.polygon([(214, 182), (214, 278), (300, 230)], fill=(255, 255, 255, 255))

ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
for rel in ["res/icon.ico", "res/tray-icon.ico", "flutter/windows/runner/resources/app_icon.ico"]:
    p = ROOT / rel
    if not p.exists():
        die(f"icon target missing: {rel}")
    base.save(p, sizes=ico_sizes)
    print(f"icon {rel}")
p = ROOT / "res/icon.png"
if not p.exists():
    die("icon target missing: res/icon.png")
base.resize((256, 256), Image.LANCZOS).save(p)

svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect x="16" y="16" width="480" height="480" rx="110" fill="#2563EB"/>
<rect x="119" y="143" width="274" height="172" rx="20" fill="none" stroke="#fff" stroke-width="30"/>
<rect x="236" y="330" width="40" height="50" fill="#fff"/>
<rect x="176" y="372" width="160" height="28" rx="14" fill="#fff"/>
<polygon points="214,182 214,278 300,230" fill="#fff"/>
</svg>
"""
if src.exists():
    import base64
    import io
    buf = io.BytesIO()
    base.resize((256, 256), Image.LANCZOS).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'viewBox="0 0 256 256"><image width="256" height="256" '
           f'xlink:href="data:image/png;base64,{b64}"/></svg>\n')
for rel in ["flutter/assets/icon.svg", "res/logo.svg"]:
    p = ROOT / rel
    if not p.exists():
        die(f"svg target missing: {rel}")
    p.write_text(svg, encoding="utf-8")
    print(f"svg {rel}")

print(f"Branding OK: name={NAME} server={SERVER or '(RustDesk public)'}")
gh_env = os.environ.get("GITHUB_ENV")
if gh_env:
    with open(gh_env, "a", encoding="utf-8") as f:
        f.write(f"RD_APP_NAME={NAME}\n")
