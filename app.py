from flask import Flask, request, send_file, jsonify, render_template
import subprocess
import os
import hashlib
import time
import logging
import threading
import glob
import base64

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

COOKIES_FILE = 'cookies.txt'
YOUTUBE_COOKIES_B64 = os.environ.get('YOUTUBE_COOKIES_B64', '')
download_status = {}

def validate_cookies_file(file_path):
    """Validate the cookies file format"""
    try:
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if it's a Netscape format cookies file
        if not content.strip():
            return False, "File is empty"
        
        # Check for Netscape format header
        lines = content.split('\n')
        if lines and 'Netscape HTTP Cookie File' in lines[0]:
            return True, "Valid Netscape format"
        else:
            # Try to check if it has proper cookie format
            for line in lines:
                if line.strip() and not line.startswith('#') and '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        return True, "Valid cookie format"
            return False, "Invalid cookie format"
            
    except Exception as e:
        return False, f"Error reading file: {str(e)}"

def setup_cookies():
    """Setup cookies from local file or environment variable"""
    # First try to use local cookies file
    if os.path.exists(COOKIES_FILE):
        is_valid, message = validate_cookies_file(COOKIES_FILE)
        if is_valid:
            logger.info(f"🍪 Using valid local cookies file: {COOKIES_FILE} - {message}")
            return COOKIES_FILE
        else:
            logger.warning(f"⚠️ Local cookies file invalid: {message}")
    
    # Fallback to environment variable
    if YOUTUBE_COOKIES_B64:
        try:
            cookies_path = '/tmp/cookies.txt'
            with open(cookies_path, 'wb') as f:
                f.write(base64.b64decode(YOUTUBE_COOKIES_B64))
            
            is_valid, message = validate_cookies_file(cookies_path)
            if is_valid:
                logger.info(f"🔐 Using valid cookies from environment variable - {message}")
                return cookies_path
            else:
                logger.warning(f"⚠️ Environment cookies invalid: {message}")
        except Exception as e:
            logger.error(f"Cookies decode error: {e}")
    
    logger.info("ℹ️ No valid cookies configured - using public access")
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
        
        # Platform-specific approaches
        if 'youtube.com' in url or 'youtu.be' in url:
            # YouTube with multiple fallback methods
            methods = [
                # Method 1: With cookies and specific format
                [
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
                    "--force-ipv4",
                    "-o", output_template
                ],
                # Method 2: Simpler approach without compatibility options
                [
                    "yt-dlp",
                    "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "--no-check-certificates",
                    "--extractor-retries", "2",
                    "--retries", "2",
                    "--fragment-retries", "2",
                    "-o", output_template
                ]
            ]
            
            # Add format options
            for method in methods:
                if format_type == 'mp3':
                    method.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
                else:
                    method.extend(["--format", "best[height<=720]"])
        
        elif 'tiktok.com' in url:
            # TikTok - simpler approach since it's working
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
            methods = [cmd]
        
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
            methods = [cmd]
        
        # Try each method
        result = None
        success = False
        
        for i, cmd in enumerate(methods):
            # Add cookies to command if available and valid
            current_cmd = cmd.copy()
            if cookies_path and os.path.exists(cookies_path):
                current_cmd.extend(["--cookies", cookies_path])
                logger.info(f"🍪 Method {i+1}: Using cookies file")
            else:
                logger.info(f"🌐 Method {i+1}: No cookies")
            
            current_cmd.append(url)
            
            logger.info(f"🔄 [{download_id}] Trying method {i+1}")
            logger.info(f"Command: {' '.join(current_cmd)}")
            
            try:
                result = subprocess.run(current_cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    logger.info(f"✅ [{download_id}] Method {i+1} succeeded")
                    success = True
                    break
                else:
                    error_msg = result.stderr or result.stdout or 'Unknown error'
                    logger.warning(f"❌ [{download_id}] Method {i+1} failed: {error_msg[:200]}")
                    # Continue to next method
            except subprocess.TimeoutExpired:
                logger.warning(f"⏰ [{download_id}] Method {i+1} timeout")
                continue
            except Exception as e:
                logger.warning(f"⚠️ [{download_id}] Method {i+1} error: {str(e)}")
                continue
        
        if success:
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
            # All methods failed
            error_output = result.stderr if result else 'No result'
            logger.error(f"❌ [{download_id}] All methods failed")
            
            if 'does not look like a Netscape format' in str(error_output):
                error_msg = "Cookies file format error. Using public access instead."
            elif 'YouTube said: ERROR' in str(error_output):
                error_msg = "YouTube is blocking access. Try a different video or use TikTok."
            else:
                error_msg = f"Download failed: {str(error_output)[:100]}..."
            
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
        
        # URL validation
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

@app.route('/api/cookies-status')
def cookies_status():
    """Endpoint to check cookies status"""
    cookies_path = setup_cookies()
    has_cookies = cookies_path and os.path.exists(cookies_path)
    
    if has_cookies:
        is_valid, message = validate_cookies_file(cookies_path)
        status_info = {
            'has_cookies': is_valid,
            'cookies_source': 'local_file' if os.path.exists(COOKIES_FILE) else 'environment',
            'message': message
        }
    else:
        status_info = {
            'has_cookies': False,
            'cookies_source': 'none',
            'message': 'No valid cookies file found'
        }
    
    return jsonify(status_info)

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
