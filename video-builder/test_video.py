"""Test tạo video từ ảnh mẫu sinh bằng Pillow."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageDraw, ImageFont
import uuid, json
from pathlib import Path

import config
import video_maker

def make_test_image(path: str, color: tuple, label: str):
    img = Image.new('RGB', (1600, 1200), color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(config.FONT_BOLD, 80)
    except Exception:
        font = ImageFont.load_default()
    draw.text((100, 500), label, fill=(255,255,255), font=font)
    # Thêm chi tiết
    for i in range(0, 1600, 80):
        draw.line([(i,0),(i,1200)], fill=(255,255,255,30), width=1)
    img.save(path, 'JPEG', quality=90)
    return path

def run_test():
    print("=== Test Video Builder ===\n")
    job_id = uuid.uuid4().hex[:8]

    # Tạo 3 ảnh test
    test_imgs = [
        {"color": (80, 50, 20),  "stage": 1, "label": "Stage 1: Foundation"},
        {"color": (60, 80, 40),  "stage": 3, "label": "Stage 3: Framework"},
        {"color": (40, 60, 120), "stage": 6, "label": "Stage 6: Complete"},
    ]

    image_items = []
    for i, info in enumerate(test_imgs):
        p = str(config.UPLOAD_DIR / f"test_{i}_{job_id}.jpg")
        make_test_image(p, info['color'], info['label'])
        image_items.append({"path": p, "stage_num": info['stage'], "order": i})
        print(f"  Created test image {i+1}: {info['label']}")

    print(f"\n  Building video from {len(image_items)} images...")

    def progress(done, total, msg):
        bar = '█' * done + '░' * (total - done)
        print(f"  [{bar}] {msg}")

    try:
        output = video_maker.build_construction_video(image_items, job_id, progress)
        size_mb = os.path.getsize(output) / (1024*1024)
        print(f"\n✅ Video created: {output}")
        print(f"   Size: {size_mb:.2f} MB")
        print(f"   Duration: {len(image_items) * config.SEGMENT_DURATION}s")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        # Cleanup test images
        for item in image_items:
            Path(item['path']).unlink(missing_ok=True)

if __name__ == '__main__':
    run_test()
