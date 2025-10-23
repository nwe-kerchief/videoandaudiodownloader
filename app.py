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
            if f.endswith(('.mp4', '.mp3', '.webm', '.txt')) and f.startswith('video_'):
                fp = os.path.join('/tmp', f)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 1800:
                    try:
                        os.remove(fp)
                        logger.info(f"🧹 Cleaned: {f}")
                    except:
                        pass
    except:
        pass

def download_video_background(download_id, url, format_type, cookies_path):
    """Background download task with full error logging"""
    try:
        download_status[download_id] = {'status': 'downloading', 'progress': 0}
        
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        base = f"video_{url_hash}_{int(time.time())}"
        
        if format_type == 'mp3':
            output_file = f"/tmp/{base}.mp3"
            cmd = [
                "yt-dlp", "-x", "--audio-format", "mp3",
                "--audio-quality", "0", "-o", output_file,
                "--no-warnings", "--no-playlist", "--no-check-certificates"
            ]
        else:
            output_file = f"/tmp/{base}.mp4"
            # Relaxed format with multiple fallbacks
            cmd = [
                "yt-dlp",
                "-f", "(bv*[vcodec^=avc]+ba)/(bv*+ba)/b[height<=720]/b",
                "--merge-output-format", "mp4",
                "-o", output_file,
                "--no-warnings", "--no-playlist", "--no-check-certificates"
            ]
        
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        
        cmd.append(url)
        
        logger.info(f"📥 [{download_id}] Command: {' '.join(cmd[:5])}...")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=600)
            
            # LOG THE OUTPUT
            if stdout:
                logger.info(f"📄 [{download_id}] stdout: {stdout[:500]}")
            if stderr:
                logger.error(f"📄 [{download_id}] stderr: {stderr[:500]}")
            
            if process.returncode == 0:
                # Check if file exists (might have different extension)
                found_file = None
                for ext in ['.mp4', '.webm', '.mkv', '.mp3', '.m4a']:
                    test_file = output_file.replace('.mp4' if format_type == 'mp4' else '.mp3', ext)
                    if os.path.exists(test_file):
                        found_file = test_file
                        break
                
                if found_file:
                    file_size = os.path.getsize(found_file)
                    size_mb = file_size / (1024 * 1024)
                    
                    if file_size > 200 * 1024 * 1024:
                        os.remove(found_file)
                        download_status[download_id] = {
                            'status': 'error',
                            'error': f'File too large: {size_mb:.1f}MB (max 200MB)'
                        }
                        logger.error(f"❌ [{download_id}] Too large: {size_mb:.1f}MB")
                    else:
                        logger.info(f"✅ [{download_id}] Ready: {size_mb:.2f}MB ({os.path.basename(found_file)})")
                        download_status[download_id] = {
                            'status': 'ready',
                            'file': found_file,
                            'size': size_mb
                        }
                else:
                    logger.error(f"❌ [{download_id}] File not found after download")
                    download_status[download_id] = {
                        'status': 'error',
                        'error': 'File not found after download'
                    }
            else:
                error_msg = stderr[:200] if stderr else 'Unknown error'
                logger.error(f"❌ [{download_id}] Failed with code {process.returncode}: {error_msg}")
                download_status[download_id] = {
                    'status': 'error',
                    'error': f'Download failed: {error_msg}'
                }
        
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error(f"⏰ [{download_id}] Timeout after 10 minutes")
            download_status[download_id] = {
                'status': 'error',
                'error': 'Download timeout (10 minutes)'
            }
    
    except Exception as e:
        logger.error(f"💥 [{download_id}] Exception: {str(e)}")
        download_status[download_id] = {
            'status': 'error',
            'error': f'Server error: {str(e)}'
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
        
        logger.info(f"🚀 [{download_id}] Started for: {url[:50]}")
        
        return jsonify({
            "download_id": download_id,
            "status": "started"
        }), 200
    
    except Exception as e:
        logger.error(f"Start error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/<download_id>')
def check_status(download_id):
    if download_id not in download_status:
        return jsonify({"error": "Not found"}), 404
    
    return jsonify(download_status[download_id]), 200

@app.route('/api/download/<download_id>')
def get_download(download_id):
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
                logger.info(f"🧹 [{download_id}] Cleaned up")
            except:
                pass
        
        return response
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "active_downloads": len(download_status)}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
