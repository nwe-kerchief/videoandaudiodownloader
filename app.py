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

def is_valid_url(url):
    """Check if URL is from YouTube or TikTok"""
    patterns = [
        r'(youtube\.com|youtu\.be)',
        r'tiktok\.com'
    ]
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)

def get_video_title(url):
    """Get video title using yt-dlp"""
    try:
        result = subprocess.run(
            ['yt-dlp', '--get-title', url],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            title = result.stdout.strip()
            # Clean filename
            title = re.sub(r'[<>:"/\\|?*]', '', title)
            return title[:100]  # Limit length
    except:
        pass
    return None

def cleanup_old_files():
    """Remove old files from /tmp"""
    try:
        for filename in os.listdir('/tmp'):
            filepath = os.path.join('/tmp', filename)
            if os.path.isfile(filepath) and (filename.endswith('.mp4') or filename.endswith('.mp3')):
                # Remove files older than 1 hour
                if os.path.getmtime(filepath) < (datetime.now().timestamp() - 3600):
                    os.remove(filepath)
                    logger.info(f"Cleaned up old file: {filename}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

@app.route('/')
def index():
    """Serve main page"""
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def download():
    """Handle download requests"""
    try:
        # Cleanup old files first
        cleanup_old_files()
        
        data = request.json
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp4')
        
        # Validate URL
        if not url:
            return jsonify({"error": "URL is required"}), 400
        
        if not is_valid_url(url):
            return jsonify({"error": "Only YouTube and TikTok URLs are supported"}), 400
        
        logger.info(f"Processing: {url}, format: {format_type}")
        
        # Generate unique filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Get video title
        video_title = get_video_title(url)
        if video_title:
            base_filename = f"{video_title}_{url_hash}"
        else:
            base_filename = f"download_{timestamp}_{url_hash}"
        
        if format_type == 'mp3':
            output_file = f"/tmp/{base_filename}.mp3"
            cmd = [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", output_file,
                "--no-warnings",
                "--no-playlist",
                url
            ]
        else:
            output_file = f"/tmp/{base_filename}.mp4"
            cmd = [
                "yt-dlp",
                "-f", "best[height<=720]/best",
                "--merge-output-format", "mp4",
                "-o", output_file,
                "--no-warnings",
                "--no-playlist",
                url
            ]
        
        logger.info(f"Running yt-dlp...")
        
        # Download with timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes
        )
        
        if result.returncode != 0:
            logger.error(f"yt-dlp error: {result.stderr}")
            return jsonify({"error": "Failed to download video. Check if URL is valid."}), 400
        
        # Find downloaded file
        if not os.path.exists(output_file):
            # yt-dlp may change extension, search for it
            possible_files = [
                f"/tmp/{base_filename}.mp4",
                f"/tmp/{base_filename}.webm",
                f"/tmp/{base_filename}.mkv",
                f"/tmp/{base_filename}.mp3",
                f"/tmp/{base_filename}.m4a"
            ]
            output_file = None
            for pf in possible_files:
                if os.path.exists(pf):
                    output_file = pf
                    break
            
            if not output_file:
                logger.error("Downloaded file not found")
                return jsonify({"error": "Downloaded file not found"}), 404
        
        logger.info(f"File downloaded: {output_file}")
        
        # Check file size
        file_size = os.path.getsize(output_file)
        logger.info(f"File size: {file_size / (1024*1024):.2f}MB")
        
        if file_size > 200 * 1024 * 1024:
            os.remove(output_file)
            return jsonify({
                "error": f"File too large: {file_size/(1024*1024):.1f}MB (limit: 200MB)"
            }), 400
        
        # Send file
        download_name = os.path.basename(output_file)
        response = send_file(
            output_file,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/octet-stream'
        )
        
        # Cleanup after sending
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(output_file):
                    os.remove(output_file)
                    logger.info(f"Cleaned up: {output_file}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
        
        return response
        
    except subprocess.TimeoutExpired:
        logger.error("Download timeout")
        return jsonify({"error": "Download timeout (10 minutes exceeded)"}), 408
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
