"""
Web Interface (Flask) - giao diện kéo thả để tạo video không cần Telegram.
Chạy song song với bot hoặc độc lập.
"""

import os
import time
import uuid
import json
import logging
import threading
from pathlib import Path
from flask import (
    Flask, render_template, request, jsonify,
    send_file, abort, url_for
)
from werkzeug.utils import secure_filename

import config
import video_maker

log = logging.getLogger(__name__)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'heic'}

# Job tracking
jobs: dict[str, dict] = {}  # job_id -> {status, progress, result, error}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html',
                           stages=config.CONSTRUCTION_STAGES,
                           segment_duration=config.SEGMENT_DURATION)


@app.route('/api/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'Không có file'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Tên file rỗng'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Định dạng không hỗ trợ (dùng JPG/PNG/WEBP)'}), 400

    fname = f"{int(time.time())}_{uuid.uuid4().hex[:6]}_{secure_filename(file.filename)}"
    save_path = str(config.UPLOAD_DIR / fname)
    file.save(save_path)

    return jsonify({'success': True, 'path': save_path, 'filename': fname})


@app.route('/api/generate', methods=['POST'])
def generate_video():
    data = request.get_json()
    if not data or 'images' not in data:
        return jsonify({'error': 'Thiếu danh sách ảnh'}), 400

    images = data['images']
    if len(images) < 1:
        return jsonify({'error': 'Cần ít nhất 1 ảnh'}), 400

    # Validate items
    for item in images:
        if not Path(item.get('path', '')).exists():
            return jsonify({'error': f"File không tồn tại: {item.get('path')}"}), 400

    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {'status': 'processing', 'progress': 0, 'message': 'Đang chuẩn bị...', 'result': None, 'error': None}

    def run_job():
        def progress_cb(done, total, msg):
            pct = int(100 * done / total) if total > 0 else 0
            jobs[job_id].update({'progress': pct, 'message': msg})

        try:
            output = video_maker.build_construction_video(images, job_id, progress_cb)
            jobs[job_id].update({'status': 'done', 'progress': 100,
                                  'message': 'Hoàn thành!', 'result': output})
        except Exception as e:
            log.exception("Job %s failed", job_id)
            jobs[job_id].update({'status': 'error', 'error': str(e)})

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({'job_id': job_id})


@app.route('/api/status/<job_id>')
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job không tồn tại'}), 404
    return jsonify(job)


@app.route('/api/download/<job_id>')
def download_video(job_id: str):
    job = jobs.get(job_id)
    if not job or job['status'] != 'done':
        abort(404)
    result_path = job['result']
    if not result_path or not Path(result_path).exists():
        abort(404)
    return send_file(result_path, as_attachment=True,
                     download_name=f"cong_trinh_{job_id}.mp4",
                     mimetype='video/mp4')


@app.route('/api/stages')
def get_stages():
    return jsonify(config.CONSTRUCTION_STAGES)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=config.WEB_PORT, debug=False)
