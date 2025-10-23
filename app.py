from flask import Flask, request, jsonify, render_template
import yt_dlp
import re
import os
import tempfile
import base64

app = Flask(__name__)

def clean_filename(filename):
    return re.sub(r'[^\w\s-]', '', filename).strip()

def setup_cookies():
    """Setup cookies from environment variable only"""
    cookies_path = None
    
    # Get cookies from environment variable (base64 encoded)
    cookies_b64 = os.environ.get('YT_COOKIES_B64')
    if cookies_b64:
        try:
            cookies_content = base64.b64decode(cookies_b64).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(cookies_content)
                cookies_path = f.name
                print("Cookies loaded from environment variable")
        except Exception as e:
            print(f"Error decoding cookies from env: {e}")
    
    return cookies_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    cookies_path = None
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Setup cookies from environment
        cookies_path = setup_cookies()

        # Configure yt-dlp
        ydl_opts = {
            'format': 'best[ext=mp4]/best[ext=webm]/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        # Add cookies if available
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
            print("Using cookies for authentication")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info without downloading
            info = ydl.extract_info(url, download=False)
            
            # Get the direct video URL
            video_url = info.get('url')
            if not video_url:
                return jsonify({'error': 'Could not extract video URL'}), 500
            
            # Get video details
            title = info.get('title', 'video')
            duration = info.get('duration')
            thumbnail = info.get('thumbnail')
            ext = info.get('ext', 'mp4')
            
            # Clean title for filename
            clean_title = clean_filename(title)
            filename = f"{clean_title}.{ext}"
            
            response_data = {
                'status': 'success',
                'title': title,
                'duration': duration,
                'thumbnail': thumbnail,
                'filename': filename,
                'download_url': video_url,
                'format': ext.upper(),
                'used_cookies': bool(cookies_path)
            }
            
            return jsonify(response_data)
            
    except Exception as e:
        error_msg = str(e)
        print(f"Download error: {error_msg}")
        return jsonify({'error': f'Download failed: {error_msg}'}), 500
    finally:
        # Clean up temporary cookies file
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.unlink(cookies_path)
            except:
                pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
