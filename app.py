from flask import Flask, request, jsonify, render_template
import yt_dlp
import re
import os
import tempfile

app = Flask(__name__)

# Clean filename for safe download
def clean_filename(filename):
    return re.sub(r'[^\w\s-]', '', filename).strip()

def setup_cookies():
    """Setup cookies from environment variable or file"""
    cookies_path = None
    
    # Option 1: Cookies from environment variable
    cookies_content = os.environ.get('YT_COOKIES')
    if cookies_content:
        # Create temporary cookies file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(cookies_content)
            cookies_path = f.name
    
    # Option 2: Cookies from file (for local development)
    elif os.path.exists('cookies.txt'):
        cookies_path = 'cookies.txt'
    
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

        # Setup cookies if available
        cookies_path = setup_cookies()

        # Configure yt-dlp with cookies
        ydl_opts = {
            'format': 'best[ext=mp4]/best[ext=webm]/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        # Add cookies if available
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
            print(f"Using cookies from: {cookies_path}")

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
        if cookies_path and cookies_path.startswith(tempfile.gettempdir()):
            try:
                os.unlink(cookies_path)
            except:
                pass

@app.route('/get_formats', methods=['POST'])
def get_formats():
    """Get available formats for a URL"""
    cookies_path = None
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Setup cookies
        cookies_path = setup_cookies()

        ydl_opts = {
            'list_formats': True,
            'quiet': True,
        }
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []
            
            for fmt in info.get('formats', []):
                formats.append({
                    'format_id': fmt.get('format_id'),
                    'ext': fmt.get('ext'),
                    'resolution': fmt.get('format_note', 'N/A'),
                    'filesize': fmt.get('filesize'),
                    'vcodec': fmt.get('vcodec', 'N/A'),
                    'acodec': fmt.get('acodec', 'N/A')
                })
            
            return jsonify({
                'title': info.get('title'),
                'formats': formats,
                'used_cookies': bool(cookies_path)
            })
            
    except Exception as e:
        return jsonify({'error': f'Failed to get formats: {str(e)}'}), 500
    finally:
        if cookies_path and cookies_path.startswith(tempfile.gettempdir()):
            try:
                os.unlink(cookies_path)
            except:
                pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
