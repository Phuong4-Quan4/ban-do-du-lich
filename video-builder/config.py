import os
import platform
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

# Video settings
SEGMENT_DURATION = 8
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
OUTPUT_FPS = 25
TRANSITION_DURATION = 1.2   # crossfade dài hơn → liền mạch hơn
VIDEO_CRF = 23
VIDEO_PRESET = 'fast'

# Audio
ENABLE_AUDIO = True     # âm thanh nền: gió, công trường, giọng người
ENABLE_TTS   = True     # giọng đọc tiếng Việt (cần internet lần đầu)

# Fonts (tự phát hiện theo hệ điều hành)
if platform.system() == 'Windows':
    _wf = Path('C:/Windows/Fonts')
    FONT_BOLD    = str(_wf / 'arialbd.ttf')   if (_wf / 'arialbd.ttf').exists() else ''
    FONT_REGULAR = str(_wf / 'arial.ttf')     if (_wf / 'arial.ttf').exists()   else ''
else:
    FONT_BOLD    = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    FONT_REGULAR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

CONSTRUCTION_STAGES = [
    {"num": 1, "name": "Chuan Bi Mat Bang",    "desc": "San lap & phan dinh cong trinh"},
    {"num": 2, "name": "Thi Cong Mong",        "desc": "Dao mong, do be tong nen"},
    {"num": 3, "name": "Xay Khung Ket Cau",    "desc": "Dung cot, dam & ket cau chiu luc"},
    {"num": 4, "name": "Xay Tuong & Vach",     "desc": "Hoan thien tuong gach & vach ngan"},
    {"num": 5, "name": "Lop Mai & Chong Tham", "desc": "Thi cong mai & he thong chong tham"},
    {"num": 6, "name": "Hoan Thien Noi That",  "desc": "Son, op lat & trang tri noi that"},
    {"num": 7, "name": "Nghiem Thu & Ban Giao", "desc": "Kiem tra tong the & ban giao cong trinh"},
]
