import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'uploads'
OUTPUT_DIR = BASE_DIR / 'output'
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '15'))
WEB_PORT = int(os.getenv('WEB_PORT', '5000'))

# Video settings - 720p to save processing & storage
SEGMENT_DURATION = 8        # giây mỗi ảnh
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
OUTPUT_FPS = 25
TRANSITION_DURATION = 0.8   # crossfade giữa các phân đoạn (s)
VIDEO_CRF = 23              # 18=tốt nhất, 28=nén nhiều nhất, 23=cân bằng
VIDEO_PRESET = 'fast'       # ultrafast/fast/medium/slow

FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REGULAR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

CONSTRUCTION_STAGES = [
    {"num": 1, "name": "Chuẩn Bị Mặt Bằng", "desc": "San lấp & phân định công trình"},
    {"num": 2, "name": "Thi Công Móng",       "desc": "Đào móng, đổ bê tông nền"},
    {"num": 3, "name": "Xây Khung Kết Cấu",   "desc": "Dựng cột, dầm & kết cấu chịu lực"},
    {"num": 4, "name": "Xây Tường & Vách",    "desc": "Hoàn thiện tường gạch & vách ngăn"},
    {"num": 5, "name": "Lợp Mái & Chống Thấm","desc": "Thi công mái & hệ thống chống thấm"},
    {"num": 6, "name": "Hoàn Thiện Nội Thất", "desc": "Sơn, ốp lát & trang trí nội thất"},
    {"num": 7, "name": "Nghiệm Thu & Bàn Giao","desc": "Kiểm tra tổng thể & bàn giao công trình"},
]
