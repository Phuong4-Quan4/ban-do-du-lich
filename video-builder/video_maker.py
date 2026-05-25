"""
Lõi xử lý video: tạo phân đoạn 8s từ ảnh + ghép liền mạch bằng FFmpeg.
Tiết kiệm chi phí: toàn bộ xử lý local, không dùng API bên ngoài.
"""

import subprocess
import os
import random
import hashlib
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config

log = logging.getLogger(__name__)

TOTAL_FRAMES = config.SEGMENT_DURATION * config.OUTPUT_FPS  # 200 frames


# ---------------------------------------------------------------------------
# Tiền xử lý ảnh
# ---------------------------------------------------------------------------

def smart_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Crop trung tâm giữ tỉ lệ khung hình."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def preprocess_image(src_path: str, dst_path: str) -> str:
    """Resize ảnh về 1280×720 và chuyển sang RGB."""
    with Image.open(src_path) as img:
        img = img.convert('RGB')
        img = smart_crop(img, config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
        img.save(dst_path, 'JPEG', quality=90)
    return dst_path


# ---------------------------------------------------------------------------
# Overlay thông tin giai đoạn
# ---------------------------------------------------------------------------

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def create_stage_overlay(stage_num: int, total_stages: int, stage_name: str,
                          stage_desc: str, dst_path: str) -> str:
    """Tạo ảnh PNG trong suốt chứa thông tin giai đoạn + thanh tiến độ."""
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Thanh gradient phía dưới
    bar_h = 90
    for y in range(bar_h):
        alpha = int(210 * (1 - y / bar_h))
        draw.rectangle([(0, h - bar_h + y), (w, h - bar_h + y + 1)],
                       fill=(10, 10, 10, alpha))

    # Thanh tiến độ màu cam
    progress_w = int(w * stage_num / total_stages)
    draw.rectangle([(0, h - 5), (progress_w, h)], fill=(255, 140, 0, 255))

    # Text giai đoạn
    font_title = _load_font(config.FONT_BOLD, 30)
    font_desc = _load_font(config.FONT_REGULAR, 18)
    font_progress = _load_font(config.FONT_REGULAR, 16)

    title_text = f"Giai doan {stage_num}/{total_stages}: {stage_name}"
    draw.text((24, h - 80), title_text, font=font_title, fill=(255, 220, 80, 255))
    draw.text((24, h - 46), stage_desc, font=font_desc, fill=(210, 210, 210, 220))

    pct = int(100 * stage_num / total_stages)
    draw.text((w - 80, h - 50), f"{pct}%", font=font_progress, fill=(255, 140, 0, 255))

    # Badge giai đoạn góc trên phải
    badge_text = f"Phase {stage_num}"
    bx, by = w - 130, 18
    draw.rounded_rectangle([(bx - 8, by - 4), (bx + 100, by + 30)],
                            radius=6, fill=(255, 140, 0, 200))
    draw.text((bx, by), badge_text, font=_load_font(config.FONT_BOLD, 18),
              fill=(10, 10, 10, 255))

    overlay.save(dst_path, 'PNG')
    return dst_path


# ---------------------------------------------------------------------------
# Tạo phân đoạn 8 giây
# ---------------------------------------------------------------------------

KEN_BURNS_EFFECTS = [
    # zoom in từ trung tâm
    "zoompan=z='min(1.0+0.0015*on,1.3)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # zoom out về trung tâm
    "zoompan=z='max(1.0,1.3-0.0015*on)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # pan trái → phải ở zoom 1.2
    "zoompan=z='1.2':d={d}:x='(iw-iw/zoom)*on/{d}':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # pan phải → trái ở zoom 1.2
    "zoompan=z='1.2':d={d}:x='(iw-iw/zoom)*(1-on/{d})':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # pan trên → dưới ở zoom 1.15
    "zoompan=z='1.15':d={d}:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*on/{d}':fps={fps}:s={w}x{h}",
]


def _choose_effect() -> str:
    tpl = random.choice(KEN_BURNS_EFFECTS)
    return tpl.format(
        d=TOTAL_FRAMES,
        fps=config.OUTPUT_FPS,
        w=config.VIDEO_WIDTH,
        h=config.VIDEO_HEIGHT,
    )


def create_segment(image_path: str, overlay_path: str,
                   output_path: str, effect_seed: int | None = None) -> str:
    """
    Tạo 1 clip 8s từ ảnh tĩnh:
      - Ken Burns effect (zoom / pan ngẫu nhiên)
      - Overlay thông tin giai đoạn
      - H.264 CRF 23 để tiết kiệm dung lượng
    """
    if effect_seed is not None:
        random.seed(effect_seed)
    kb = _choose_effect()

    vf = (
        f"[0:v]{kb}[kb];"
        f"[kb][1:v]overlay=0:0[out]"
    )

    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-loop', '1', '-framerate', str(config.OUTPUT_FPS), '-i', image_path,
        '-i', overlay_path,
        '-filter_complex', vf,
        '-map', '[out]',
        '-t', str(config.SEGMENT_DURATION),
        '-c:v', 'libx264',
        '-preset', config.VIDEO_PRESET,
        '-crf', str(config.VIDEO_CRF),
        '-pix_fmt', 'yuv420p',
        '-r', str(config.OUTPUT_FPS),
        output_path,
    ]
    log.debug("FFmpeg segment: %s", ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error:\n{result.stderr}")
    return output_path


# ---------------------------------------------------------------------------
# Ghép các phân đoạn với crossfade
# ---------------------------------------------------------------------------

def merge_segments(segment_paths: list[str], output_path: str,
                   transition: float = config.TRANSITION_DURATION) -> str:
    """
    Ghép nhiều clip 8s thành 1 video liền mạch bằng xfade.
    Offset mỗi clip = (duration - transition) * index
    """
    n = len(segment_paths)
    if n == 0:
        raise ValueError("Không có phân đoạn nào để ghép")
    if n == 1:
        import shutil
        shutil.copy(segment_paths[0], output_path)
        return output_path

    inputs = []
    for p in segment_paths:
        inputs += ['-i', p]

    # Xây dựng filter_complex chuỗi xfade
    filters = []
    prev_label = '[0:v]'
    step = config.SEGMENT_DURATION - transition

    for i in range(1, n):
        offset = round(step * i - transition * (i - 1), 3)
        next_input = f'[{i}:v]'
        out_label = '[v_out]' if i == n - 1 else f'[v{i}]'
        filters.append(
            f"{prev_label}{next_input}xfade=transition=fade:"
            f"duration={transition}:offset={offset}{out_label}"
        )
        prev_label = out_label

    filter_complex = ';'.join(filters)

    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        *inputs,
        '-filter_complex', filter_complex,
        '-map', '[v_out]',
        '-c:v', 'libx264',
        '-preset', config.VIDEO_PRESET,
        '-crf', str(config.VIDEO_CRF),
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        output_path,
    ]
    log.debug("FFmpeg merge: %s", ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge error:\n{result.stderr}")
    return output_path


# ---------------------------------------------------------------------------
# Pipeline đầy đủ
# ---------------------------------------------------------------------------

def build_construction_video(image_items: list[dict], job_id: str,
                              progress_cb=None) -> str:
    """
    image_items: [{"path": "/...", "stage_num": 1, "order": 0}, ...]
    Trả về đường dẫn video cuối cùng.
    """
    items = sorted(image_items, key=lambda x: (x.get('stage_num', 1), x.get('order', 0)))
    total = len(items)
    stages = config.CONSTRUCTION_STAGES

    tmp_dir = config.OUTPUT_DIR / f"tmp_{job_id}"
    tmp_dir.mkdir(exist_ok=True)

    segment_paths = []
    try:
        for idx, item in enumerate(items):
            stage_num = item.get('stage_num', 1)
            stage_info = next(
                (s for s in stages if s['num'] == stage_num),
                {"name": f"Giai đoạn {stage_num}", "desc": ""}
            )

            if progress_cb:
                progress_cb(idx, total, f"Đang xử lý ảnh {idx+1}/{total}...")

            # 1. Tiền xử lý ảnh
            scaled = str(tmp_dir / f"scaled_{idx:03d}.jpg")
            preprocess_image(item['path'], scaled)

            # 2. Tạo overlay
            overlay = str(tmp_dir / f"overlay_{idx:03d}.png")
            create_stage_overlay(
                stage_num=stage_num,
                total_stages=total,
                stage_name=stage_info['name'],
                stage_desc=stage_info['desc'],
                dst_path=overlay,
            )

            # 3. Tạo phân đoạn 8s
            seg = str(tmp_dir / f"seg_{idx:03d}.mp4")
            create_segment(scaled, overlay, seg, effect_seed=idx)
            segment_paths.append(seg)

        if progress_cb:
            progress_cb(total, total, "Đang ghép video...")

        # 4. Ghép tất cả phân đoạn
        output_path = str(config.OUTPUT_DIR / f"construction_{job_id}.mp4")
        merge_segments(segment_paths, output_path)

    finally:
        # Dọn dẹp file tạm
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path
