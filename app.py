from flask import Flask, request, send_file, jsonify, render_template
import subprocess
import os
import hashlib
import re
from datetime import datetime
import logging
import threading
import time

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')
download_status = {}

def setup_cookies():
    if not YOUTUBE_COOKIES:
        return None
    try:
        cookies_path = '/tmp/cookies.txt'
        with open(cookies_path, 'w', encoding='utf-8') as f:
            f.write(YOUTUBE_COOKIES)
        return cookies_path
    except:
        return None

def is_valid_url(url):
    patterns = [r'(youtube\.com|youtu\.be)', r'tiktok\.com']
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)

def cleanup_old_files():
    try:
        now = time.time()
        for f in os.listdir('/tmp'):
            if f.endswith(('.mp4', '.mp3', '.webm', '.txt')):
                fp = os.path.join('/tmp', f)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 1800:
                    try:
                        os.remove(fp)
                    except:
                        pass
    except:
        pass

def download_video_background(download_id, url, format_type, cookies_path):
    """Background download task"""
    try:
        download_status[download_id] = {'status': 'downloading', 'progress': 0}
        
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        base = f"video_{url_hash}_{int(time.time())}"
        
        if format_type == 'mp3':
            output_file = f"/tmp/{base}.mp3"
            cmd = [
                "yt-dlp", "-x", "--audio-format", "mp3",
                "--audio-quality", "0", "-o", output_file,
                "--no-warnings", "--no-playlist"
            ]
        else:
            output_file = f"/tmp/{base}.mp4"
            # RELAXED format selection (fallback to any format if H.264 not available)
            cmd = [
                "yt-dlp",
                "-f", "bv*[vcodec^=avc][height<=720]+ba/bv[height<=720]+ba/b[height<=720]/b",
                "--merge-output-format", "mp4",
                "-o", output_file,
                "--no-warnings", "--no-playlist"
            ]
        
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        
        cmd.append(url)
        
        logger.info(f"📥 [{download_id}] Downloading...")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=600)
            
            if process.returncode == 0 and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                size_mb = file_size / (1024 * 1024)
                
                if file_size > 200 * 1024 * 1024:
                    os.remove(output_file)
                    download_status[download_id] = {
                        'status': 'error',
                        'error': f'File too large: {size_mb:.1f}MB'
                    }
                else:
                    logger.info(f"✅ [{download_id}] Ready: {size_mb:.2f}MB")
                    download_status[download_id] = {
                        'status': 'ready',
                        'file': output_file,
                        'size': size_mb
                    }
            else:
                logger.error(f"❌ [{download_id}] Failed")
                download_status[download_id] = {
                    'status': 'error',
                    'error': 'Download failed. Check URL.'
                }
        
        except subprocess.TimeoutExpired:
            process.kill()
            download_status[download_id] = {
                'status': 'error',
                'error': 'Timeout (10 minutes)'
            }
    
    except Exception as e:
        logger.error(f"❌ [{download_id}] Error: {e}")
        download_status[download_id] = {
            'status': 'error',
            'error': str(e)
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start-download', methods=['POST'])
def start_download():
    """Start background download"""
    try:
        cleanup_old_files()
        
        data = request.json
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp4')
        
        if not url:
            return jsonify({"error": "URL required"}), 400
        
        if not is_valid_url(url):
            return jsonify({"error": "Only YouTube/TikTok supported"}), 400
        
        download_id = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:12]
        cookies_path = setup_cookies()
        
        thread = threading.Thread(
            target=download_video_background,
            args=(download_id, url, format_type, cookies_path)
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"🚀 [{download_id}] Started")
        
        return jsonify({
            "download_id": download_id,
            "status": "started"
        }), 200
    
    except Exception as e:
        logger.error(f"Start error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/<download_id>')
def check_status(download_id):
    """Check download status"""
    if download_id not in download_status:
        return jsonify({"error": "Not found"}), 404
    
    return jsonify(download_status[download_id]), 200

@app.route('/api/download/<download_id>')
def get_download(download_id):
    """Download file"""
    try:
        if download_id not in download_status:
            return jsonify({"error": "Not found"}), 404
        
        status = download_status[download_id]
        
        if status['status'] != 'ready':
            return jsonify({"error": "Not ready"}), 400
        
        file_path = status['file']
        
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path),
            mimetype='application/octet-stream'
        )
        
        @response.call_on_close
        def cleanup():
            try:
                time.sleep(5)
                if os.path.exists(file_path):
                    os.remove(file_path)
                if download_id in download_status:
                    del download_status[download_id]
                logger.info(f"🧹 [{download_id}] Cleaned")
            except:
                pass
        
        return response
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
