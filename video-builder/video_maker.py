"""
Lõi xử lý video:
- Mỗi ảnh → clip 8s với hiệu ứng Ken Burns tốc độ cao (cảm giác tua nhanh)
- Âm thanh: giọng đọc TTS tiếng Việt + gió + tiếng công trường + giọng người
- Hiệu ứng ánh nắng (warm color grade)
- Ghép liền mạch: xfade video + acrossfade audio dài 1.2s
"""

import subprocess
import os
import random
import logging
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

import config

log = logging.getLogger(__name__)
TOTAL_FRAMES = config.SEGMENT_DURATION * config.OUTPUT_FPS  # 200 frames


# ---------------------------------------------------------------------------
# Tiền xử lý ảnh
# ---------------------------------------------------------------------------

def smart_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def preprocess_image(src: str, dst: str) -> str:
    with Image.open(src) as img:
        img = img.convert('RGB')
        img = smart_crop(img, config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
        img.save(dst, 'JPEG', quality=92)
    return dst


# ---------------------------------------------------------------------------
# Overlay thông tin giai đoạn
# ---------------------------------------------------------------------------

def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def create_stage_overlay(stage_num: int, total_stages: int,
                          stage_name: str, stage_desc: str, dst: str) -> str:
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient dưới
    bar_h = 95
    for y in range(bar_h):
        a = int(220 * (1 - y / bar_h))
        draw.rectangle([(0, h - bar_h + y), (w, h - bar_h + y + 1)], fill=(8, 8, 8, a))

    # Thanh tiến độ cam
    pw = int(w * stage_num / total_stages)
    draw.rectangle([(0, h - 6), (pw, h)], fill=(255, 140, 0, 255))

    # Chấm tròn trên thanh tiến độ
    draw.ellipse([(pw - 6, h - 11), (pw + 6, h + 1)], fill=(255, 200, 50, 255))

    # Text
    f_big  = _font(config.FONT_BOLD, 28)
    f_med  = _font(config.FONT_REGULAR, 17)
    f_pct  = _font(config.FONT_BOLD, 22)

    draw.text((22, h - 84), f"Giai doan {stage_num}/{total_stages}: {stage_name}",
              font=f_big, fill=(255, 218, 60, 255))
    draw.text((22, h - 50), stage_desc, font=f_med, fill=(210, 210, 210, 215))
    pct = int(100 * stage_num / total_stages)
    draw.text((w - 75, h - 70), f"{pct}%", font=f_pct, fill=(255, 140, 0, 255))

    # Badge góc trên phải
    bx, by = w - 136, 16
    draw.rounded_rectangle([(bx - 8, by - 4), (bx + 108, by + 32)],
                            radius=7, fill=(255, 140, 0, 210))
    draw.text((bx, by), f"Phase {stage_num}", font=_font(config.FONT_BOLD, 17),
              fill=(15, 15, 15, 255))

    img.save(dst, 'PNG')
    return dst


# ---------------------------------------------------------------------------
# Ken Burns — tốc độ cao để tạo cảm giác tua nhanh / năng động
# ---------------------------------------------------------------------------

_KB = [
    # zoom in mạnh
    "zoompan=z='min(1.0+0.0035*on,1.5)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # zoom out mạnh
    "zoompan=z='max(1.0,1.5-0.0035*on)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # pan trái→phải tốc độ cao @ zoom 1.35
    "zoompan=z='1.35':d={d}:x='(iw-iw/zoom)*on/{d}':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # pan phải→trái @ zoom 1.35
    "zoompan=z='1.35':d={d}:x='(iw-iw/zoom)*(1-on/{d})':y='ih/2-(ih/zoom/2)':fps={fps}:s={w}x{h}",
    # diagonal pan (trên-trái → dưới-phải)
    "zoompan=z='1.3':d={d}:x='(iw-iw/zoom)*on/{d}':y='(ih-ih/zoom)*on/{d}':fps={fps}:s={w}x{h}",
    # zoom in + pan lên
    "zoompan=z='min(1.0+0.003*on,1.4)':d={d}:x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{d})':fps={fps}:s={w}x{h}",
]

# Warm color grade = hiệu ứng nắng vàng
_SUNSHINE = (
    "curves=r='0/0 0.35/0.42 0.65/0.74 1/1'"
    ":g='0/0 0.35/0.35 0.65/0.68 1/0.94'"
    ":b='0/0 0.35/0.26 0.65/0.58 1/0.80',"
    "eq=brightness=0.04:saturation=1.35:contrast=1.12"
)


def _pick_kb(seed: int | None = None) -> str:
    if seed is not None:
        random.seed(seed)
    return random.choice(_KB).format(
        d=TOTAL_FRAMES, fps=config.OUTPUT_FPS,
        w=config.VIDEO_WIDTH, h=config.VIDEO_HEIGHT
    )


# ---------------------------------------------------------------------------
# Tạo âm thanh: TTS + gió + công trường + giọng người
# ---------------------------------------------------------------------------

def _has_audio_stream(path: str) -> bool:
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', path],
        capture_output=True, text=True
    )
    return '"codec_type": "audio"' in r.stdout


def create_audio(stage_name: str, stage_desc: str, stage_num: int,
                 duration: float, out: str) -> bool:
    """
    Tạo audio: TTS giọng Việt + gió + tiếng búa/máy + tiếng người xa.
    Fallback về ambient nếu TTS lỗi (offline).
    """
    tts_raw = out + '_tts.mp3'
    tts_ok = False

    if config.ENABLE_TTS:
        try:
            from gtts import gTTS
            text = f"Giai doan {stage_num}. {stage_name}. {stage_desc}."
            gTTS(text=text, lang='vi', slow=False).save(tts_raw)
            tts_ok = Path(tts_raw).exists() and Path(tts_raw).stat().st_size > 1000
        except Exception as e:
            log.warning("gTTS: %s", e)

    dur1 = duration + 1  # lavfi cần dài hơn 1 chút

    if tts_ok:
        out_st = max(1.0, duration - 1.5)
        filt = (
            # TTS: trim, fade, delay 0.8s
            f"[0:a]atrim=0:{duration:.1f},"
            f"afade=t=in:d=0.5,afade=t=out:st={out_st:.1f}:d=0.8,"
            f"adelay=800|800,volume=1.3[tts];"
            # Gió: pink noise → lowpass
            "[1:a]lowpass=f=620,highpass=f=75,volume=0.38[wind];"
            # Tiếng máy/búa: brown noise → bandpass thấp
            "[2:a]lowpass=f=380,highpass=f=120,volume=0.32[mach];"
            # Giọng người xa: pink noise bandpass trung
            "[3:a]lowpass=f=3200,highpass=f=500,volume=0.14[crowd];"
            # Trộn ambient
            "[wind][mach][crowd]amix=inputs=3:duration=longest[amb];"
            # Trộn TTS + ambient
            "[amb][tts]amix=inputs=2:weights='0.45 1':normalize=0,volume=1.4[out]"
        )
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-i', tts_raw,
            '-f', 'lavfi', '-t', str(dur1), '-i', 'anoisesrc=c=pink:a=0.07',
            '-f', 'lavfi', '-t', str(dur1), '-i', 'anoisesrc=c=brown:a=0.09',
            '-f', 'lavfi', '-t', str(dur1), '-i', 'anoisesrc=c=pink:a=0.04',
            '-filter_complex', filt,
            '-map', '[out]', '-t', str(duration),
            '-ar', '44100', '-ac', '2', out,
        ]
    else:
        # Chỉ ambient
        filt = (
            "[0:a]lowpass=f=620,highpass=f=75,volume=0.45[wind];"
            "[1:a]lowpass=f=380,highpass=f=120,volume=0.38[mach];"
            "[2:a]lowpass=f=3200,highpass=f=500,volume=0.18[crowd];"
            "[wind][mach][crowd]amix=inputs=3:duration=longest,volume=1.8[out]"
        )
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-f', 'lavfi', '-t', str(dur1), '-i', 'anoisesrc=c=pink:a=0.07',
            '-f', 'lavfi', '-t', str(dur1), '-i', 'anoisesrc=c=brown:a=0.09',
            '-f', 'lavfi', '-t', str(dur1), '-i', 'anoisesrc=c=pink:a=0.04',
            '-filter_complex', filt,
            '-map', '[out]', '-t', str(duration),
            '-ar', '44100', '-ac', '2', out,
        ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    Path(tts_raw).unlink(missing_ok=True)

    if r.returncode != 0:
        log.warning("Audio gen failed: %s", r.stderr[:200])
        return False
    return True


# ---------------------------------------------------------------------------
# Tạo phân đoạn 8 giây (ảnh + overlay + audio + ánh nắng)
# ---------------------------------------------------------------------------

def create_segment(image_path: str, overlay_path: str,
                   audio_path: str | None, output_path: str,
                   effect_seed: int | None = None) -> str:
    kb = _pick_kb(effect_seed)

    # filter_complex: zoompan → overlay → sunshine
    vf = (
        f"[0:v]{kb}[kb];"
        f"[kb][1:v]overlay=0:0[ov];"
        f"[ov]{_SUNSHINE}[out]"
    )

    use_audio = audio_path and Path(audio_path).exists()

    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-loop', '1', '-framerate', str(config.OUTPUT_FPS), '-i', image_path,
        '-i', overlay_path,
    ]
    if use_audio:
        cmd += ['-i', audio_path]

    cmd += ['-filter_complex', vf, '-map', '[out]']
    if use_audio:
        cmd += ['-map', '2:a']

    cmd += [
        '-t', str(config.SEGMENT_DURATION),
        '-c:v', 'libx264', '-preset', config.VIDEO_PRESET, '-crf', str(config.VIDEO_CRF),
        '-pix_fmt', 'yuv420p', '-r', str(config.OUTPUT_FPS),
    ]
    if use_audio:
        cmd += ['-c:a', 'aac', '-b:a', '128k']

    cmd.append(output_path)

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Segment error:\n{r.stderr[-500:]}")
    return output_path


# ---------------------------------------------------------------------------
# Ghép liền mạch: xfade video + acrossfade audio
# ---------------------------------------------------------------------------

def merge_segments(paths: list[str], output_path: str,
                   t: float = config.TRANSITION_DURATION) -> str:
    n = len(paths)
    if n == 0:
        raise ValueError("Không có phân đoạn")
    if n == 1:
        shutil.copy(paths[0], output_path)
        return output_path

    has_audio = _has_audio_stream(paths[0])
    inputs = []
    for p in paths:
        inputs += ['-i', p]

    v_parts, a_parts = [], []
    pv, pa = '[0:v]', '[0:a]'
    step = config.SEGMENT_DURATION - t   # khoảng offset mỗi clip

    for i in range(1, n):
        offset = round(step * i - t * (i - 1), 3)
        nv = f'[{i}:v]'
        na = f'[{i}:a]'
        ov = '[v_out]' if i == n - 1 else f'[v{i}]'
        oa = '[a_out]' if i == n - 1 else f'[a{i}]'

        # Video: crossfade mượt
        v_parts.append(
            f"{pv}{nv}xfade=transition=fade:duration={t}:offset={offset}{ov}"
        )
        # Audio: acrossfade khớp thời gian
        if has_audio:
            a_parts.append(f"{pa}{na}acrossfade=d={t}{oa}")

        pv, pa = ov, oa

    fc = ';'.join(v_parts)
    if has_audio and a_parts:
        fc += ';' + ';'.join(a_parts)

    maps = ['-map', '[v_out]']
    if has_audio:
        maps += ['-map', '[a_out]']

    codec = [
        '-c:v', 'libx264', '-preset', config.VIDEO_PRESET, '-crf', str(config.VIDEO_CRF),
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    ]
    if has_audio:
        codec += ['-c:a', 'aac', '-b:a', '128k']

    cmd = ['ffmpeg', '-y', '-loglevel', 'error', *inputs,
           '-filter_complex', fc, *maps, *codec, output_path]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Merge error:\n{r.stderr[-500:]}")
    return output_path


# ---------------------------------------------------------------------------
# Pipeline đầy đủ
# ---------------------------------------------------------------------------

def build_construction_video(image_items: list[dict], job_id: str,
                              progress_cb=None) -> str:
    items = sorted(image_items,
                   key=lambda x: (x.get('stage_num', 1), x.get('order', 0)))
    total = len(items)

    tmp = config.OUTPUT_DIR / f"tmp_{job_id}"
    tmp.mkdir(exist_ok=True)
    segs = []

    try:
        for idx, item in enumerate(items):
            sn = item.get('stage_num', 1)
            si = next((s for s in config.CONSTRUCTION_STAGES if s['num'] == sn),
                      {"name": f"Giai doan {sn}", "desc": ""})

            if progress_cb:
                progress_cb(idx, total, f"Xu ly anh {idx+1}/{total}: {si['name']}")

            scaled  = str(tmp / f"sc_{idx:03d}.jpg")
            overlay = str(tmp / f"ov_{idx:03d}.png")
            audio   = str(tmp / f"au_{idx:03d}.mp3")
            seg     = str(tmp / f"sg_{idx:03d}.mp4")

            preprocess_image(item['path'], scaled)
            create_stage_overlay(sn, total, si['name'], si['desc'], overlay)

            audio_ok = False
            if config.ENABLE_AUDIO:
                audio_ok = create_audio(si['name'], si['desc'], sn,
                                        config.SEGMENT_DURATION, audio)

            create_segment(scaled, overlay,
                           audio if audio_ok else None,
                           seg, effect_seed=idx)
            segs.append(seg)

        if progress_cb:
            progress_cb(total, total, "Dang ghep video va am thanh lien mach...")

        out = str(config.OUTPUT_DIR / f"construction_{job_id}.mp4")
        merge_segments(segs, out)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return out
