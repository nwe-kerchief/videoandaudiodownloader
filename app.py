from flask import Flask, request, send_file, jsonify, render_template
import subprocess
import os
import hashlib
import re
from datetime import datetime
import logging

app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get cookies from environment variable
YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')

def setup_cookies():
    """Create cookies.txt from environment variable"""
    if not YOUTUBE_COOKIES:
        return None
    try:
        cookies_path = '/tmp/cookies.txt'
        with open(cookies_path, 'w', encoding='utf-8') as f:
            f.write(YOUTUBE_COOKIES)
        logger.info("✅ Cookies created")
        return cookies_path
    except Exception as e:
        logger.error(f"Cookies error: {e}")
        return None

def is_valid_url(url):
    """Check if URL is from YouTube or TikTok"""
    patterns = [r'(youtube\.com|youtu\.be)', r'tiktok\.com']
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)

def get_video_title(url, cookies_path):
    """Get video title using yt-dlp"""
    try:
        cmd = ['yt-dlp', '--get-title', url, '--no-warnings']
        if cookies_path:
            cmd.extend(['--cookies', cookies_path])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            title = result.stdout.strip()
            title = re.sub(r'[<>:"/\\|?*]', '', title)
            return title[:80]
    except:
        pass
    return None

def convert_hevc_to_h264(input_file):
    """Convert HEVC/H265 to H264 for Windows Media Player"""
    try:
        # Check codec
        probe = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', input_file
        ], capture_output=True, text=True, timeout=10)
        
        codec = probe.stdout.strip().lower()
        logger.info(f"Video codec: {codec}")
        
        # Only convert if HEVC
        if codec not in ['hevc', 'h265']:
            return input_file
        
        logger.info("🔄 Converting HEVC to H264...")
        output_file = input_file.replace('.mp4', '_h264.mp4')
        
        # Convert with ffmpeg
        subprocess.run([
            'ffmpeg', '-i', input_file,
            '-c:v', 'libx264',
            '-crf', '23',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y', output_file
        ], check=True, capture_output=True, timeout=600)
        
        if os.path.exists(output_file):
            os.remove(input_file)
            logger.info("✅ Converted to H264")
            return output_file
        
        return input_file
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return input_file

def cleanup_old_files():
    """Remove old temp files"""
    try:
        now = datetime.now().timestamp()
        for f in os.listdir('/tmp'):
            if f.endswith(('.mp4', '.mp3', '.webm')):
                fp = os.path.join('/tmp', f)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 3600:
                    os.remove(fp)
    except:
        pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def download():
    """Handle download requests"""
    output_file = None
    try:
        cleanup_old_files()
        cookies_path = setup_cookies()
        
        data = request.json
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp4')
        
        if not url:
            return jsonify({"error": "URL required"}), 400
        
        if not is_valid_url(url):
            return jsonify({"error": "Only YouTube and TikTok supported"}), 400
        
        logger.info(f"📥 Downloading: {url} ({format_type})")
        
        # Generate filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        video_title = get_video_title(url, cookies_path)
        
        if video_title:
            base = f"{video_title}_{url_hash}"
        else:
            base = f"download_{url_hash}"
        
        # Build command
        if format_type == 'mp3':
            output_file = f"/tmp/{base}.mp3"
            cmd = [
                "yt-dlp", "-x", "--audio-format", "mp3",
                "--audio-quality", "0", "-o", output_file,
                "--no-warnings", "--no-playlist"
            ]
        else:
            output_file = f"/tmp/{base}.mp4"
            cmd = [
                "yt-dlp", "-f", "best[height<=720]/best",
                "--merge-output-format", "mp4",
                "-o", output_file,
                "--no-warnings", "--no-playlist"
            ]
        
        # Add cookies
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        
        cmd.append(url)
        
        # Download
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            logger.error(f"yt-dlp failed: {result.stderr}")
            return jsonify({"error": "Download failed. Check URL or try again."}), 400
        
        # Find file
        if not os.path.exists(output_file):
            # Try alternate extensions
            for ext in ['.webm', '.mkv', '.m4a']:
                alt = output_file.replace('.mp4' if format_type == 'mp4' else '.mp3', ext)
                if os.path.exists(alt):
                    output_file = alt
                    break
            
            if not os.path.exists(output_file):
                return jsonify({"error": "File not found after download"}), 404
        
        logger.info(f"✅ Downloaded: {os.path.basename(output_file)}")
        
        # CONVERT HEVC TO H264 (TikTok fix)
        if format_type == 'mp4':
            output_file = convert_hevc_to_h264(output_file)
        
        # Check size
        file_size = os.path.getsize(output_file)
        size_mb = file_size / (1024 * 1024)
        logger.info(f"📦 Size: {size_mb:.2f}MB")
        
        if file_size > 200 * 1024 * 1024:
            os.remove(output_file)
            return jsonify({"error": f"File too large: {size_mb:.1f}MB (max 200MB)"}), 400
        
        # Send file
        download_name = os.path.basename(output_file)
        
        @after_this_request
        def cleanup(response):
            try:
                if output_file and os.path.exists(output_file):
                    os.remove(output_file)
                    logger.info(f"🧹 Cleaned: {os.path.basename(output_file)}")
            except:
                pass
            return response
        
        return send_file(
            output_file,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/octet-stream'
        )
        
    except subprocess.TimeoutExpired:
        if output_file and os.path.exists(output_file):
            os.remove(output_file)
        return jsonify({"error": "Download timeout (10 min limit)"}), 408
    
    except Exception as e:
        if output_file and os.path.exists(output_file):
            os.remove(output_file)
        logger.error(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def after_this_request(func):
    """Decorator for cleanup after response"""
    if not hasattr(app, 'after_request_funcs_stack'):
        app.after_request_funcs_stack = []
    app.after_request_funcs_stack.append(func)
    return func

@app.after_request
def call_after_request_funcs(response):
    """Execute cleanup functions"""
    if hasattr(app, 'after_request_funcs_stack'):
        for func in app.after_request_funcs_stack:
            response = func(response)
        app.after_request_funcs_stack = []
    return response

@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
