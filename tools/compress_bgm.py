"""压缩背景音乐为网页友好格式

用法: python tools/compress_bgm.py
需要 ffmpeg 在 PATH 中或已通过 winget 安装
"""
import subprocess, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sound", "background.mp3")
DST = os.path.join(ROOT, "web", "explorer", "sound", "background.mp3")

# 查找 ffmpeg
FFMPEG = None
for loc in [
    "ffmpeg",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),
]:
    if loc.endswith("Packages"):
        # 遍历 WinGet 包查找 ffmpeg
        if not os.path.isdir(loc):
            continue
        for root, dirs, files in os.walk(loc):
            for f in files:
                if f.lower() == "ffmpeg.exe":
                    FFMPEG = os.path.join(root, f)
                    break
            if FFMPEG:
                break
    else:
        if subprocess.run(["where", loc], capture_output=True, shell=True).returncode == 0:
            FFMPEG = loc
            break

if not FFMPEG:
    print("[ERROR] 未找到 ffmpeg。请运行: winget install ffmpeg")
    sys.exit(1)

if not os.path.exists(SRC):
    print(f"[ERROR] 源文件不存在: {SRC}")
    sys.exit(1)

orig_mb = os.path.getsize(SRC) / (1024 * 1024)
print(f"源文件: {SRC} ({orig_mb:.0f} MB)")
print(f"目标:   {DST}")

# 压缩参数：64kbps, mono, 22050Hz - 适合网页背景音乐循环播放
cmd = [
    FFMPEG, "-y",
    "-i", SRC,
    "-codec:a", "libmp3lame",
    "-b:a", "64k",
    "-ac", "1",          # mono
    "-ar", "22050",      # 采样率
    "-q:a", "5",         # 质量 (0-9, 越小越好)
    DST,
]

print(f"执行: {' '.join(cmd[-5:])}")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    new_mb = os.path.getsize(DST) / (1024 * 1024)
    print(f"\n[DONE] 压缩完成: {orig_mb:.0f} MB -> {new_mb:.1f} MB (节省 {(1 - new_mb/orig_mb)*100:.0f}%)")
else:
    print(f"[ERROR] ffmpeg 失败:\n{result.stderr}")
    sys.exit(1)
