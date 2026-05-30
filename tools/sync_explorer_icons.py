"""将 assets/icons_generated/ 最新图标同步到 web/explorer/assets/icons/ 稳定文件名。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_DIR = REPO / "assets" / "icons_generated"
DST_DIR = REPO / "web" / "explorer" / "assets" / "icons"

ICON_IDS = (
    "icon_miner",
    "icon_smelter",
    "icon_assembler",
    "icon_refiner",
    "icon_printer",
    "icon_power_plant",
    "icon_power_core",
    "icon_storage",
    "icon_resource_energy",
    "icon_resource_parts",
    "icon_resource_food",
    "icon_resource_medical",
    "icon_resource_intel",
    "icon_tab_current",
    "icon_tab_upcoming",
    "icon_tab_management",
    "icon_tab_explore",
    "icon_tab_dossier",
    "icon_tab_tutorial",
    "icon_favicon",
)


def asset_basename(icon_id: str) -> str:
    if icon_id == "icon_favicon":
        return "favicon"
    if icon_id.startswith("icon_"):
        return icon_id[len("icon_") :]
    return icon_id


def find_latest(icon_id: str) -> Path | None:
    prefix = f"{icon_id}_"
    matches = [p for p in SRC_DIR.glob(f"{prefix}*") if p.is_file()]
    if not matches:
        matches = list(SRC_DIR.glob(f"{asset_basename(icon_id)}.*"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def main() -> int:
    if not SRC_DIR.is_dir():
        print(f"缺少目录：{SRC_DIR}")
        return 1
    DST_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    missing: list[str] = []
    for iid in ICON_IDS:
        src = find_latest(iid)
        if not src:
            missing.append(iid)
            continue
        name = asset_basename(iid)
        dst = DST_DIR / f"{name}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        print(f"  {iid} -> {dst.relative_to(REPO)}")
        ok += 1
    print(f"\n已同步 {ok}/{len(ICON_IDS)}")
    if missing:
        print("未找到：", ", ".join(missing))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
