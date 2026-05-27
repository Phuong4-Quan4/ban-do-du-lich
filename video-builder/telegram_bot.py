"""
Telegram Bot - polling mode (không cần server/webhook).
Workflow:
  1. /start hay /new → bắt đầu phiên mới
  2. Gửi ảnh → bot hỏi giai đoạn bằng nút bấm
  3. /generate → tạo video
  4. Bot gửi lại file video MP4
"""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import config
import video_maker

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session manager (in-memory, đủ cho production nhỏ)
# ---------------------------------------------------------------------------

class SessionManager:
    """Lưu trạng thái mỗi người dùng."""
    def __init__(self):
        self._sessions: dict[int, dict] = {}

    def get(self, user_id: int) -> dict:
        if user_id not in self._sessions:
            self._sessions[user_id] = self._new()
        return self._sessions[user_id]

    def _new(self) -> dict:
        return {
            'images': [],       # [{"path": ..., "stage_num": ..., "order": ...}]
            'pending_path': None,   # ảnh đang chờ chọn giai đoạn
            'job_id': str(uuid.uuid4())[:8],
        }

    def reset(self, user_id: int):
        self._sessions[user_id] = self._new()

    def add_image(self, user_id: int, path: str, stage_num: int):
        s = self.get(user_id)
        order = len(s['images'])
        s['images'].append({'path': path, 'stage_num': stage_num, 'order': order})

    def set_pending(self, user_id: int, path: str):
        self.get(user_id)['pending_path'] = path

    def pop_pending(self, user_id: int) -> str | None:
        s = self.get(user_id)
        p = s.get('pending_path')
        s['pending_path'] = None
        return p


sessions = SessionManager()


# ---------------------------------------------------------------------------
# Keyboard helpers
# ---------------------------------------------------------------------------

def stage_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Bàn phím chọn giai đoạn thi công."""
    buttons = []
    row = []
    for st in config.CONSTRUCTION_STAGES:
        cb = f"stage:{user_id}:{st['num']}"
        row.append(InlineKeyboardButton(f"{st['num']}. {st['name']}", callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions.reset(uid)
    text = (
        "*Chào mừng đến với Video Xây Dựng Bot!* 🏗\n\n"
        "Bot giúp bạn tạo video tiến độ thi công từ ảnh thực tế.\n\n"
        "*Cách dùng:*\n"
        "1️⃣ Gửi ảnh công trình (JPEG/PNG)\n"
        "2️⃣ Chọn giai đoạn thi công cho mỗi ảnh\n"
        "3️⃣ Gửi /generate để tạo video\n\n"
        "*Lệnh:*\n"
        "/new — Bắt đầu phiên mới\n"
        "/list — Xem ảnh đã thêm\n"
        "/generate — Tạo video\n"
        "/stages — Danh sách giai đoạn\n"
        "/clear — Xóa phiên hiện tại\n"
        "/help — Hướng dẫn chi tiết"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions.reset(uid)
    await update.message.reply_text(
        "✅ Phiên mới đã được tạo. Hãy gửi ảnh công trình để bắt đầu!"
    )


async def cmd_stages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["*Các giai đoạn thi công:*\n"]
    for s in config.CONSTRUCTION_STAGES:
        lines.append(f"*{s['num']}.* {s['name']}\n   _{s['desc']}_")
    await update.message.reply_text('\n'.join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    imgs = sessions.get(uid)['images']
    if not imgs:
        await update.message.reply_text("Chưa có ảnh nào. Hãy gửi ảnh để bắt đầu!")
        return
    stage_map = {s['num']: s['name'] for s in config.CONSTRUCTION_STAGES}
    lines = [f"*Danh sách ảnh ({len(imgs)} ảnh):*\n"]
    for i, im in enumerate(imgs, 1):
        sn = im['stage_num']
        sname = stage_map.get(sn, f"Giai đoạn {sn}")
        lines.append(f"{i}. Giai đoạn {sn} – {sname}")
    await update.message.reply_text('\n'.join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions.reset(uid)
    await update.message.reply_text("🗑 Đã xóa toàn bộ phiên. Gửi ảnh mới để bắt đầu lại.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "*Hướng dẫn chi tiết:*\n\n"
        "📸 *Gửi ảnh:* Gửi từng ảnh công trình. Bot sẽ hỏi giai đoạn.\n"
        "🔢 *Chọn giai đoạn:* Nhấn nút tương ứng với giai đoạn trong ảnh.\n"
        "🎬 *Tạo video:* Gửi /generate sau khi thêm đủ ảnh (ít nhất 2 ảnh).\n"
        "📥 *Nhận video:* Bot sẽ gửi file MP4 về sau khi xử lý xong.\n\n"
        "*Lưu ý:*\n"
        "• Mỗi ảnh = 1 phân đoạn 8 giây với hiệu ứng Ken Burns\n"
        "• Các phân đoạn được ghép liền mạch bằng crossfade\n"
        "• Ảnh được sắp xếp theo thứ tự giai đoạn thi công\n"
        "• Hỗ trợ ảnh JPEG/PNG tối đa 15MB"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message

    # Lấy ảnh chất lượng cao nhất
    photo = msg.photo[-1] if msg.photo else None
    if not photo:
        return

    # Kiểm tra kích thước (~15MB)
    if photo.file_size and photo.file_size > config.MAX_FILE_SIZE_MB * 1024 * 1024:
        await msg.reply_text(
            f"❌ Ảnh quá lớn (tối đa {config.MAX_FILE_SIZE_MB}MB). Vui lòng gửi ảnh nhỏ hơn."
        )
        return

    wait_msg = await msg.reply_text("⏳ Đang tải ảnh...")

    # Lưu ảnh vào thư mục uploads
    job_id = sessions.get(uid)['job_id']
    fname = f"{uid}_{job_id}_{int(time.time())}.jpg"
    save_path = str(config.UPLOAD_DIR / fname)

    tg_file = await photo.get_file()
    await tg_file.download_to_drive(save_path)

    sessions.set_pending(uid, save_path)
    await wait_msg.delete()

    total = len(sessions.get(uid)['images'])
    await msg.reply_text(
        f"✅ Đã nhận ảnh! (Tổng: {total + 1} ảnh)\n\n*Ảnh này thuộc giai đoạn nào?*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=stage_keyboard(uid),
    )


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Hỗ trợ gửi ảnh dưới dạng file để giữ chất lượng gốc."""
    uid = update.effective_user.id
    doc = update.message.document
    if not doc or not doc.mime_type:
        return
    if not doc.mime_type.startswith('image/'):
        await update.message.reply_text("❌ Chỉ hỗ trợ file ảnh (JPEG/PNG/WEBP).")
        return
    if doc.file_size and doc.file_size > config.MAX_FILE_SIZE_MB * 1024 * 1024:
        await update.message.reply_text(
            f"❌ File quá lớn (tối đa {config.MAX_FILE_SIZE_MB}MB)."
        )
        return

    wait_msg = await update.message.reply_text("⏳ Đang tải file ảnh...")
    job_id = sessions.get(uid)['job_id']
    ext = doc.mime_type.split('/')[-1].replace('jpeg', 'jpg')
    fname = f"{uid}_{job_id}_{int(time.time())}.{ext}"
    save_path = str(config.UPLOAD_DIR / fname)

    tg_file = await doc.get_file()
    await tg_file.download_to_drive(save_path)

    sessions.set_pending(uid, save_path)
    await wait_msg.delete()

    total = len(sessions.get(uid)['images'])
    await update.message.reply_text(
        f"✅ Đã nhận file ảnh! (Tổng: {total + 1} ảnh)\n\n*Ảnh này thuộc giai đoạn nào?*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=stage_keyboard(uid),
    )


async def handle_stage_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng bấm nút chọn giai đoạn."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(':')
    if len(parts) != 3 or parts[0] != 'stage':
        return

    uid = int(parts[1])
    stage_num = int(parts[2])

    pending = sessions.pop_pending(uid)
    if not pending:
        await query.edit_message_text("⚠️ Không tìm thấy ảnh đang chờ. Vui lòng gửi lại ảnh.")
        return

    sessions.add_image(uid, pending, stage_num)
    stage_info = next((s for s in config.CONSTRUCTION_STAGES if s['num'] == stage_num),
                      {"name": f"Giai đoạn {stage_num}"})
    total = len(sessions.get(uid)['images'])

    await query.edit_message_text(
        f"✅ Đã thêm vào *Giai đoạn {stage_num}: {stage_info['name']}*\n"
        f"📊 Tổng cộng: {total} ảnh\n\n"
        f"Tiếp tục gửi ảnh hoặc /generate để tạo video.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_generate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    imgs = sessions.get(uid)['images']

    if len(imgs) < 1:
        await update.message.reply_text(
            "❌ Cần ít nhất 1 ảnh để tạo video. Hãy gửi ảnh trước!"
        )
        return

    job_id = sessions.get(uid)['job_id']
    status_msg = await update.message.reply_text(
        f"🎬 Đang tạo video từ {len(imgs)} ảnh...\n"
        f"⏳ Mỗi ảnh ~{config.SEGMENT_DURATION}s. Vui lòng đợi."
    )

    async def update_status(done: int, total: int, msg: str):
        bar_len = 10
        filled = int(bar_len * done / total) if total > 0 else 0
        bar = '█' * filled + '░' * (bar_len - filled)
        pct = int(100 * done / total) if total > 0 else 0
        try:
            await status_msg.edit_text(
                f"🎬 Đang xử lý video...\n"
                f"[{bar}] {pct}%\n"
                f"📌 {msg}"
            )
        except Exception:
            pass

    # Chạy video_maker trong thread pool để không block event loop
    loop = asyncio.get_event_loop()

    progress_data = {'done': 0, 'total': len(imgs), 'msg': ''}

    def sync_progress(done, total, msg):
        progress_data.update({'done': done, 'total': total, 'msg': msg})

    try:
        output_path = await loop.run_in_executor(
            None,
            lambda: video_maker.build_construction_video(imgs, job_id, sync_progress)
        )
    except Exception as e:
        log.exception("Video creation failed")
        await status_msg.edit_text(f"❌ Lỗi khi tạo video:\n`{str(e)[:300]}`",
                                    parse_mode=ParseMode.MARKDOWN)
        return

    await status_msg.edit_text("✅ Video đã tạo xong! Đang gửi...")

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    total_duration = len(imgs) * config.SEGMENT_DURATION

    with open(output_path, 'rb') as f:
        await update.message.reply_video(
            video=f,
            caption=(
                f"🏗 *Video Tiến Độ Thi Công*\n\n"
                f"📸 {len(imgs)} ảnh | ⏱ {total_duration}s | 💾 {file_size_mb:.1f}MB\n"
                f"Tạo bởi Construction Video Bot"
            ),
            parse_mode=ParseMode.MARKDOWN,
            supports_streaming=True,
        )

    await status_msg.delete()

    # Reset job_id cho phiên mới nhưng giữ ảnh
    sessions.reset(uid)
    await update.message.reply_text(
        "🎉 Hoàn thành! Phiên mới đã được tạo.\n"
        "Gửi /new để bắt đầu dự án mới hoặc tiếp tục gửi ảnh."
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run_bot(token: str):
    app = (
        Application.builder()
        .token(token)
        .build()
    )

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('new', cmd_new))
    app.add_handler(CommandHandler('stages', cmd_stages))
    app.add_handler(CommandHandler('list', cmd_list))
    app.add_handler(CommandHandler('clear', cmd_clear))
    app.add_handler(CommandHandler('help', cmd_help))
    app.add_handler(CommandHandler('generate', cmd_generate))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    app.add_handler(CallbackQueryHandler(handle_stage_callback, pattern=r'^stage:'))

    log.info("Bot đang chạy ở chế độ polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    if not config.TELEGRAM_TOKEN:
        print("❌ Thiếu TELEGRAM_TOKEN trong file .env")
        exit(1)
    run_bot(config.TELEGRAM_TOKEN)
