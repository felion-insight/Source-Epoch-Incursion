"""批量压缩 web/explorer/assets 下的图片资源

策略：
  - 图标 (1024→256px): resize + RGBA→调色板(P模式) → 预计 1MB → 30KB
  - 设施贴图 (1200→600px): resize 50% + 压缩 → 预计 1.3MB → 150KB
  - 立绘 (1024→512px):  resize 50% + compress → 预计 900KB → 120KB
  - 地块贴图:          不缩放, 重新压缩 JPEG quality=70 → 预计 1MB → 300KB

运行前需安装 Pillow:  pip install Pillow
使用方式:  python tools/compress_assets.py [--dry-run] [--no-resize]
"""

import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "web", "explorer", "assets")
BACKUP_DIR = os.path.join(ASSETS, "_backup_before_compress")

# ── 配置 ──────────────────────────────────────────
ICON_SIZE         = 256          # 图标缩放到此尺寸（原 1024）
FACILITY_SIZE_W   = 600          # 设施贴图最大宽度（原 1200）
PORTRAIT_SIZE_W   = 512          # 立绘最大宽度（原 1024）
JPEG_QUALITY      = 75           # JPEG 重新压缩质量
PNG_OPTIMIZE      = True         # PNG 优化开关

DRY_RUN           = "--dry-run" in sys.argv
NO_RESIZE         = "--no-resize" in sys.argv


def fmt_kb(n):
    return f"{n // 1024:,} KB"


def compress_png_as_palette(fp, max_size=None):
    """将 RGBA PNG 转为调色板模式（保留透明），可选缩放"""
    img = Image.open(fp).convert("RGBA")
    orig_w, orig_h = img.size
    if max_size and not NO_RESIZE and max(orig_w, orig_h) > max_size:
        ratio = max_size / max(orig_w, orig_h)
        new_w = max(1, int(orig_w * ratio))
        new_h = max(1, int(orig_h * ratio))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # 转为调色板 + alpha（FASTOCTREE 支持 RGBA）
    if img.mode == "RGBA":
        try:
            img = img.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
        except Exception:
            # 如果量化失败，保持 RGBA 仅做 resize
            pass
    img.info.pop("icc_profile", None)
    img.info.pop("exif", None)
    return img


def compress_png_rgba(fp, max_w=None):
    """压缩 RGBA PNG，可选缩放宽度"""
    img = Image.open(fp)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    if max_w and not NO_RESIZE and img.width > max_w:
        ratio = max_w / img.width
        new_h = max(1, int(img.height * ratio))
        img = img.resize((max_w, new_h), Image.LANCZOS)
    img.info.pop("icc_profile", None)
    img.info.pop("exif", None)
    return img


def compress_jpg(fp, quality=JPEG_QUALITY):
    """重新压缩 JPEG"""
    img = Image.open(fp)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.info.pop("icc_profile", None)
    img.info.pop("exif", None)
    return img, quality


def backup_original(fp, rel):
    """复制原文件到备份目录"""
    dest = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(fp, "rb") as src:
        with open(dest, "wb") as dst:
            dst.write(src.read())


def save_image(img, fp, **kwargs):
    """保存图片，PNG 用 optimize，JPEG 用 quality"""
    ext = os.path.splitext(fp)[1].lower()
    if ext in (".jpg", ".jpeg"):
        quality = kwargs.get("quality", JPEG_QUALITY)
        img.save(fp, "JPEG", quality=quality, optimize=True)
    else:
        img.save(fp, "PNG", optimize=PNG_OPTIMIZE)


def process_file(fp, rel, category):
    """处理单个文件，返回 (原大小, 新大小)"""
    orig_size = os.path.getsize(fp)

    if DRY_RUN:
        return orig_size, None

    # 备份
    backup_original(fp, rel)

    try:
        if category == "icon":
            img = compress_png_as_palette(fp, max_size=ICON_SIZE)
            save_image(img, fp)
        elif category == "facility":
            img = compress_png_rgba(fp, max_w=FACILITY_SIZE_W)
            save_image(img, fp)
        elif category == "portrait":
            ext = os.path.splitext(fp)[1].lower()
            if ext in (".jpg", ".jpeg"):
                img, q = compress_jpg(fp)
                save_image(img, fp, quality=q)
            else:
                img = compress_png_rgba(fp, max_w=PORTRAIT_SIZE_W)
                save_image(img, fp)
        elif category == "tile":
            ext = os.path.splitext(fp)[1].lower()
            if ext in (".jpg", ".jpeg"):
                img, q = compress_jpg(fp)
                save_image(img, fp, quality=q)
            else:
                img = compress_png_rgba(fp)
                save_image(img, fp)
        else:
            return orig_size, None

        new_size = os.path.getsize(fp)
        return orig_size, new_size
    except Exception as e:
        print(f"  [WARN] 跳过 {rel}: {e}")
        # 从备份恢复
        backup_path = os.path.join(BACKUP_DIR, rel)
        if os.path.exists(backup_path):
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(backup_path, "rb") as src:
                with open(fp, "wb") as dst:
                    dst.write(src.read())
        return orig_size, None


def main():
    if DRY_RUN:
        print("[DRY RUN] 不会修改任何文件\n")

    categories = {
        os.path.join(ASSETS, "icons"):      "icon",
        os.path.join(ASSETS, "facilities"): "facility",
        os.path.join(ASSETS, "portraits"):  "portrait",
        ASSETS:                             "tile",  # 根目录下的 tile_*/walkable_*
    }

    tile_names = {"tile_build.jpg", "tile_road.jpg", "tile_void.jpg", "walkable_floor_tile.png"}

    items = []
    for base_dir, cat in categories.items():
        for f in sorted(os.listdir(base_dir)):
            fp = os.path.join(base_dir, f)
            if not os.path.isfile(fp):
                continue
            if not f.lower().endswith((".png", ".jpg", ".jpeg")):
                continue
            if cat == "tile" and f not in tile_names:
                continue
            items.append((fp, cat))

    total_orig = 0
    total_new = 0
    saved = 0

    print(f"{'文件':<40s} {'分类':<10s} {'原大小':>10s} {'新大小':>10s} {'节省':>8s}")
    print("-" * 90)

    for fp, cat in items:
        orig, new = process_file(fp, os.path.relpath(fp, ASSETS), cat)
        total_orig += orig
        fname = os.path.basename(fp)
        if new is not None:
            total_new += new
            saved += (orig - new)
            pct = (1 - new / orig) * 100 if orig else 0
            print(f"{fname:<40s} {cat:<10s} {fmt_kb(orig):>10s} {fmt_kb(new):>10s} {pct:>6.0f}%")
        else:
            total_new += orig
            if DRY_RUN:
                print(f"{fname:<40s} {cat:<10s} {fmt_kb(orig):>10s} {'(dry-run)':>10s} {'-':>8s}")
            else:
                print(f"{fname:<40s} {cat:<10s} {fmt_kb(orig):>10s} {'(跳过)':>10s} {'-':>8s}")

    print("-" * 90)
    if DRY_RUN:
        print(f"\n[DRY RUN] 预计处理 {len(items)} 个文件，原始总大小: {fmt_kb(total_orig)}")
        print("   去掉 --dry-run 参数以实际执行压缩。")
    else:
        pct = (1 - total_new / total_orig) * 100 if total_orig else 0
        print(f"\n[DONE] 压缩完成: {fmt_kb(total_orig)} -> {fmt_kb(total_new)}  (节省 {pct:.0f}%)")
        print(f"   原文件备份在: {BACKUP_DIR}")
        print(f"   如需还原: 将备份目录内容复制回 assets/ 即可")


if __name__ == "__main__":
    main()
