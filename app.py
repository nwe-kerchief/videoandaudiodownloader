from flask import Flask, request, send_file, jsonify, render_template
import subprocess
import os
import hashlib
import time
import logging
import threading
import glob
import base64
import requests
import json

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

YOUTUBE_COOKIES_B64 = os.environ.get('YOUTUBE_COOKIES_B64', '')
download_status = {}

def setup_cookies():
    if not YOUTUBE_COOKIES_B64:
        return None
    try:
        cookies_path = '/tmp/cookies.txt'
        with open(cookies_path, 'wb') as f:
            f.write(base64.b64decode(YOUTUBE_COOKIES_B64))
        return cookies_path
    except Exception as e:
        logger.error(f"Cookies decode error: {e}")
        return None

def cleanup_old_files():
    try:
        now = time.time()
        for f in os.listdir('/tmp'):
            if f.startswith('video_'):
                fp = os.path.join('/tmp', f)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 1800:
                    try:
                        os.remove(fp)
                    except:
                        pass
    except:
        pass

def download_video_background(download_id, url, format_type, cookies_path):
    try:
        download_status[download_id] = {'status': 'downloading'}
        
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = int(time.time())
        output_template = f"/tmp/video_{url_hash}_{timestamp}.%(ext)s"
        
        # Try different approaches based on platform
        if 'youtube.com' in url or 'youtu.be' in url:
            # YouTube specific approach
            cmd = [
                "yt-dlp",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--no-check-certificates",
                "--extractor-retries", "2",
                "--retries", "2", 
                "--fragment-retries", "2",
                "--throttled-rate", "100K",
                "--compat-options", "youtube-dl",
                "--no-part",
                "--no-mtime",
                "-o", output_template
            ]
            
            if format_type == 'mp3':
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            else:
                cmd.extend(["--format", "best[height<=480]"])
                
        elif 'tiktok.com' in url:
            # TikTok specific approach - use simpler format selection
            cmd = [
                "yt-dlp",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--no-check-certificates",
                "--extractor-retries", "2",
                "--retries", "2",
                "--fragment-retries", "2",
                "-o", output_template
            ]
            
            if format_type == 'mp3':
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            else:
                # For TikTok, don't specify format and let yt-dlp choose
                pass
        else:
            # Generic approach
            cmd = [
                "yt-dlp",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", 
                "--no-check-certificates",
                "--extractor-retries", "2",
                "--retries", "2",
                "--fragment-retries", "2",
                "-o", output_template
            ]
            
            if format_type == 'mp3':
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        
        cmd.append(url)
        
        logger.info(f"📥 [{download_id}] Downloading from {url}")
        logger.info(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            files = glob.glob(f"/tmp/video_{url_hash}_{timestamp}.*")
            
            if files:
                file_path = files[0]
                file_size = os.path.getsize(file_path)
                size_mb = file_size / (1024 * 1024)
                
                if file_size > 300 * 1024 * 1024:
                    os.remove(file_path)
                    download_status[download_id] = {
                        'status': 'error',
                        'error': f'File too large: {size_mb:.1f}MB (max 300MB)'
                    }
                else:
                    logger.info(f"✅ [{download_id}] Ready: {size_mb:.2f}MB")
                    download_status[download_id] = {
                        'status': 'ready',
                        'file': file_path,
                        'size': size_mb
                    }
            else:
                download_status[download_id] = {'status': 'error', 'error': 'File not found after download'}
        else:
            error_output = result.stderr or result.stdout or 'Unknown error'
            logger.error(f"❌ [{download_id}] Download failed: {error_output[:500]}")
            
            # Provide more specific error messages
            if 'YouTube said: ERROR' in error_output:
                error_msg = "YouTube is blocking downloads from this server. Try a different video or use TikTok."
            elif 'Requested format is not available' in error_output:
                error_msg = "This video format is not available. Try downloading as MP3 instead."
            elif 'Video unavailable' in error_output:
                error_msg = "This video is unavailable or restricted."
            else:
                error_msg = f"Download failed: {error_output[:100]}..."
            
            download_status[download_id] = {'status': 'error', 'error': error_msg}
    
    except subprocess.TimeoutExpired:
        logger.error(f"❌ [{download_id}] Download timeout")
        download_status[download_id] = {'status': 'error', 'error': 'Timeout (5 minutes)'}
    except Exception as e:
        logger.error(f"❌ [{download_id}] Unexpected error: {str(e)}")
        download_status[download_id] = {'status': 'error', 'error': f'Unexpected error: {str(e)}'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start-download', methods=['POST'])
def start_download():
    try:
        cleanup_old_files()
        
        data = request.json
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp4')
        
        if not url:
            return jsonify({"error": "URL required"}), 400
        
        # Basic URL validation
        supported_domains = ['youtube.com', 'youtu.be', 'tiktok.com', 'vm.tiktok.com']
        if not any(domain in url for domain in supported_domains):
            return jsonify({"error": f"Only {', '.join(supported_domains)} URLs are supported"}), 400
        
        download_id = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:12]
        cookies_path = setup_cookies()
        
        thread = threading.Thread(
            target=download_video_background,
            args=(download_id, url, format_type, cookies_path)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({"download_id": download_id}), 200
    
    except Exception as e:
        logger.error(f"Start download error: {str(e)}")
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
        
        filename = os.path.basename(file_path)
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )
        
        @response.call_on_close
        def cleanup():
            try:
                time.sleep(5)
                if os.path.exists(file_path):
                    os.remove(file_path)
                if download_id in download_status:
                    del download_status[download_id]
            except:
                pass
        
        return response
    
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
