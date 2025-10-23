from flask import Flask, request, jsonify, render_template
import yt_dlp
import re
import os

app = Flask(__name__)

# Clean filename for safe download
def clean_filename(filename):
    return re.sub(r'[^\w\s-]', '', filename).strip()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Configure yt-dlp to get direct URL without downloading
        ydl_opts = {
            'format': 'best[ext=mp4]/best[ext=webm]/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

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
                'format': ext.upper()
            }
            
            return jsonify(response_data)
            
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/get_formats', methods=['POST'])
def get_formats():
    """Get available formats for a URL"""
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        ydl_opts = {
            'list_formats': True,
            'quiet': True,
        }

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
                'formats': formats
            })
            
    except Exception as e:
        return jsonify({'error': f'Failed to get formats: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)