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
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')

# Track downloads in memory
download_status = {}

def setup_cookies():
    if not YOUTUBE_COOKIES:
        return None
    try:
        cookies_path = '/tmp/cookies.txt'
        with open(cookies_path, 'w', encoding='utf-8') as f:
            f.write(YOUTUBE_COOKIES)
        logger.info("✅ Cookies ready")
        return cookies_path
    except Exception as e:
        logger.error(f"Cookie error: {e}")
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
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 1800:  # 30 min
                    try:
                        os.remove(fp)
                        logger.info(f"🧹 Cleaned: {f}")
                    except:
                        pass
    except:
        pass

def download_video_background(download_id, url, format_type, cookies_path):
    """Background download task"""
    try:
        download_status[download_id] = {'status': 'downloading', 'progress': 0}
        
        # Generate filename
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
            # Force H.264 codec
            cmd = [
                "yt-dlp",
                "-f", "bv*[vcodec^=avc][height<=720]+ba/b[vcodec^=avc][height<=720]/b[height<=720]",
                "--merge-output-format", "mp4",
                "-o", output_file,
                "--no-warnings", "--no-playlist", "--no-check-certificates"
            ]
        
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        
        cmd.append(url)
        
        logger.info(f"📥 [{download_id}] Starting download...")
        
        # Run download
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait with timeout
        try:
            stdout, stderr = process.communicate(timeout=600)  # 10 min
            
            if process.returncode == 0 and os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                size_mb = file_size / (1024 * 1024)
                
                if file_size > 200 * 1024 * 1024:
                    os.remove(output_file)
                    download_status[download_id] = {
                        'status': 'error',
                        'error': f'File too large: {size_mb:.1f}MB (max 200MB)'
                    }
                else:
                    logger.info(f"✅ [{download_id}] Downloaded: {size_mb:.2f}MB")
                    download_status[download_id] = {
                        'status': 'ready',
                        'file': output_file,
                        'size': size_mb
                    }
            else:
                logger.error(f"❌ [{download_id}] Failed: {stderr[:200]}")
                download_status[download_id] = {
                    'status': 'error',
                    'error': 'Download failed. Check URL or try again.'
                }
        
        except subprocess.TimeoutExpired:
            process.kill()
            download_status[download_id] = {
                'status': 'error',
                'error': 'Download timeout (10 minutes)'
            }
    
    except Exception as e:
        logger.error(f"❌ [{download_id}] Exception: {e}")
        download_status[download_id] = {
            'status': 'error',
            'error': str(e)
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start-download', methods=['POST'])
def start_download():
    """Start download in background, return immediately"""
    try:
        cleanup_old_files()
        
        data = request.json
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp4')
        
        if not url:
            return jsonify({"error": "URL required"}), 400
        
        if not is_valid_url(url):
            return jsonify({"error": "Only YouTube and TikTok supported"}), 400
        
        # Generate download ID
        download_id = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:12]
        
        # Setup cookies
        cookies_path = setup_cookies()
        
        # Start background download
        thread = threading.Thread(
            target=download_video_background,
            args=(download_id, url, format_type, cookies_path)
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"🚀 [{download_id}] Started background download")
        
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
        return jsonify({"error": "Download not found"}), 404
    
    return jsonify(download_status[download_id]), 200

@app.route('/api/download/<download_id>')
def get_download(download_id):
    """Get downloaded file"""
    try:
        if download_id not in download_status:
            return jsonify({"error": "Download not found"}), 404
        
        status = download_status[download_id]
        
        if status['status'] != 'ready':
            return jsonify({"error": "File not ready"}), 400
        
        file_path = status['file']
        
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        # Send file
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path),
            mimetype='application/octet-stream'
        )
        
        # Cleanup after sending
        @response.call_on_close
        def cleanup():
            try:
                time.sleep(5)  # Wait before deleting
                if os.path.exists(file_path):
                    os.remove(file_path)
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
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))  # Default 10000 for Render
    app.run(host='0.0.0.0', port=port, debug=False)
