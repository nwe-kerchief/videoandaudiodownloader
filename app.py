from flask import Flask, request, send_file, jsonify, render_template
import subprocess
import os
import hashlib
import time
import logging
import threading
import glob
import re
import shutil

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Configuration
COOKIES_FILE = 'cookies.txt'
MAX_FILE_SIZE = 300 * 1024 * 1024  # 300MB for web version
download_status = {}

def setup_cookies():
    """Setup cookies from local file"""
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if content:
                # Count valid cookie lines
                lines = content.split('\n')
                valid_lines = 0
                for line in lines:
                    if line.strip() and not line.startswith('#') and '\t' in line:
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            valid_lines += 1
                
                if valid_lines > 0:
                    logger.info(f"🍪 Using local cookies file with {valid_lines} valid cookies")
                    return COOKIES_FILE
                else:
                    logger.warning("⚠️ Cookies file exists but no valid cookie lines found")
            else:
                logger.warning("⚠️ Cookies file is empty")
                
        except Exception as e:
            logger.error(f"❌ Error reading cookies file: {e}")
    
    logger.info("ℹ️ No valid cookies - using public access")
    return None

def cleanup_old_files():
    """Clean up old downloaded files"""
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

def clear_tmp_directory():
    """Clear temporary directory"""
    for file in glob.glob('/tmp/*.mp3') + glob.glob('/tmp/*.mp4') + glob.glob('/tmp/*.m4a') + glob.glob('/tmp/*.webm'):
        try: 
            os.remove(file)
        except: 
            pass

def download_video_background(download_id, url, format_type, cookies_path):
    """Background download function using SIMPLE Telegram bot logic"""
    try:
        download_status[download_id] = {'status': 'downloading'}
        
        # Clear temp directory
        clear_tmp_directory()
        
        # Generate unique output template
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = int(time.time())
        safe_filename = f"video_{url_hash}_{timestamp}"
        output_template = f"/tmp/{safe_filename}.%(ext)s"
        
        # Build SIMPLE download command - NO format specifications
        if format_type == 'mp3':
            # Simple audio download
            base_command = [
                "yt-dlp", "-x", "--audio-format", "mp3",
                "-o", output_template, 
                "--no-warnings"
            ]
        else:
            # Simple video download - let yt-dlp choose the best format
            base_command = [
                "yt-dlp", 
                "-o", output_template,
                "--no-warnings"
            ]
        
        # Add cookies if available - use original file directly
        if cookies_path and os.path.exists(cookies_path):
            base_command.extend(["--cookies", cookies_path])
            logger.info(f"🍪 [{download_id}] Using cookies file directly")
        
        base_command.append(url)
        
        logger.info(f"📥 [{download_id}] Starting simple download")
        logger.info(f"Command: {' '.join(base_command)}")
        
        # Execute download
        result = subprocess.run(base_command, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            logger.error(f"❌ [{download_id}] Download failed: {error_msg[:500]}")
            
            # Try without cookies if cookies failed
            if cookies_path and 'cookies.txt' in error_msg:
                logger.info(f"🔄 [{download_id}] Trying without cookies")
                base_command_no_cookies = [cmd for cmd in base_command if cmd != '--cookies' and cmd != cookies_path]
                result = subprocess.run(base_command_no_cookies, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    process_downloaded_file(download_id, format_type, safe_filename)
                else:
                    download_status[download_id] = {'status': 'error', 'error': 'Download failed. Try a different video.'}
            else:
                download_status[download_id] = {'status': 'error', 'error': 'Download failed. Try a different video or format.'}
            return
        
        # Process the downloaded file
        process_downloaded_file(download_id, format_type, safe_filename)
        
    except subprocess.TimeoutExpired:
        logger.error(f"❌ [{download_id}] Download timeout")
        download_status[download_id] = {'status': 'error', 'error': 'Timeout (10 minutes)'}
    except Exception as e:
        logger.error(f"❌ [{download_id}] Unexpected error: {str(e)}")
        download_status[download_id] = {'status': 'error', 'error': f'Unexpected error: {str(e)}'}

def process_downloaded_file(download_id, format_type, safe_filename):
    """Process downloaded file"""
    # Find downloaded file
    files = os.listdir('/tmp')
    logger.info(f"📂 Files in /tmp: {files}")
    
    # Look for files with our pattern
    downloaded_files = []
    for f in files:
        if safe_filename in f:
            downloaded_files.append(f)
    
    # If no files with our pattern, look for any media files (recent ones)
    if not downloaded_files:
        if format_type == 'mp3':
            # Get all audio files sorted by modification time (newest first)
            audio_files = []
            for f in files:
                if f.endswith(('.mp3', '.m4a', '.webm', '.opus')):
                    file_path = f"/tmp/{f}"
                    audio_files.append((f, os.path.getmtime(file_path)))
            
            if audio_files:
                audio_files.sort(key=lambda x: x[1], reverse=True)
                downloaded_files = [audio_files[0][0]]
        else:
            # Get all video files sorted by modification time (newest first)
            video_files = []
            for f in files:
                if f.endswith(('.mp4', '.webm', '.mkv')):
                    file_path = f"/tmp/{f}"
                    video_files.append((f, os.path.getmtime(file_path)))
            
            if video_files:
                video_files.sort(key=lambda x: x[1], reverse=True)
                downloaded_files = [video_files[0][0]]
    
    logger.info(f"✅ Downloaded files: {downloaded_files}")
    
    if not downloaded_files:
        logger.error("❌ No files found after download")
        download_status[download_id] = {'status': 'error', 'error': 'No files found after download'}
        return
    
    file_path = f"/tmp/{downloaded_files[-1]}"
    logger.info(f"📦 Using file: {file_path}")
    
    file_size = os.path.getsize(file_path)
    size_mb = file_size / (1024 * 1024)
    
    # Check file size
    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        download_status[download_id] = {
            'status': 'error',
            'error': f'File too large: {size_mb:.1f}MB (max {MAX_FILE_SIZE/1024/1024}MB)'
        }
        return
    
    # Get display title from filename
    display_title = downloaded_files[-1]
    for ext in ['.mp3', '.mp4', '.m4a', '.webm', '.opus', '.mkv']:
        if display_title.endswith(ext):
            display_title = display_title[:-len(ext)]
    
    logger.info(f"✅ [{download_id}] Ready: {size_mb:.2f}MB - {display_title}")
    download_status[download_id] = {
        'status': 'ready',
        'file': file_path,
        'size': size_mb,
        'title': display_title
    }

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
        
        # Determine filename and MIME type
        filename = os.path.basename(file_path)
        title = status.get('title', 'download')
        
        if filename.endswith('.mp3'):
            download_name = f"{title}.mp3"
            mimetype = 'audio/mpeg'
        elif filename.endswith('.mp4'):
            download_name = f"{title}.mp4" 
            mimetype = 'video/mp4'
        elif filename.endswith('.webm'):
            download_name = f"{title}.webm"
            mimetype = 'video/webm'
        elif filename.endswith('.m4a'):
            download_name = f"{title}.m4a"
            mimetype = 'audio/mp4'
        else:
            download_name = filename
            mimetype = 'application/octet-stream'
        
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
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
    
    if cookies_path and os.path.exists(cookies_path):
        try:
            with open(cookies_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                lines = content.split('\n')
                valid_cookies = sum(1 for line in lines if line.strip() and not line.startswith('#') and '\t' in line)
            
            return jsonify({
                'has_cookies': True,
                'cookies_source': 'github_file',
                'message': f'{valid_cookies} cookies loaded',
                'valid_cookies': valid_cookies
            })
        except Exception as e:
            return jsonify({
                'has_cookies': False,
                'cookies_source': 'github_file',
                'message': f'Error reading cookies: {str(e)}'
            })
    
    return jsonify({
        'has_cookies': False,
        'cookies_source': 'none',
        'message': 'No cookies file found'
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
