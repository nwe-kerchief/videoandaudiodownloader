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
    """Setup cookies from environment variable"""
    cookies_path = None
    cookies_b64 = os.environ.get('YT_COOKIES_B64')
    
    if cookies_b64:
        try:
            cookies_content = base64.b64decode(cookies_b64).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(cookies_content)
                cookies_path = f.name
                print("✅ Cookies loaded from environment")
        except Exception as e:
            print(f"❌ Error decoding cookies: {e}")
    
    return cookies_path

def format_size(bytes_size):
    """Convert bytes to human readable format"""
    if not bytes_size:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def format_duration(seconds):
    """Convert seconds to MM:SS"""
    if not seconds:
        return "Unknown"
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_formats', methods=['POST'])
def get_formats():
    """Get all available formats for a video"""
    cookies_path = None
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        print(f"🔍 Processing URL: {url}")
        cookies_path = setup_cookies()

        # Enhanced yt-dlp options with better format extraction
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            # Force better format extraction
            'format': 'bestvideo+bestaudio/best',
            'ignoreerrors': True,
        }
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
            print("🔑 Using cookies for authentication")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"📹 Video title: {info.get('title')}")
            print(f"📊 Available formats: {len(info.get('formats', []))}")
            
            # Debug: Print all available formats
            for i, fmt in enumerate(info.get('formats', [])):
                print(f"Format {i}: {fmt.get('format_id')} | {fmt.get('ext')} | {fmt.get('format_note')} | {fmt.get('vcodec')} | {fmt.get('acodec')}")
            
            # Organize formats by type
            video_formats = []
            audio_formats = []
            
            for fmt in info.get('formats', []):
                format_info = {
                    'format_id': fmt.get('format_id'),
                    'ext': fmt.get('ext', 'unknown'),
                    'resolution': fmt.get('format_note', 'N/A'),
                    'filesize': fmt.get('filesize'),
                    'filesize_readable': format_size(fmt.get('filesize')),
                    'vcodec': fmt.get('vcodec', 'none'),
                    'acodec': fmt.get('acodec', 'none'),
                    'quality': fmt.get('quality', 0),
                    'url': fmt.get('url')  # For debugging
                }
                
                # Better format categorization
                has_video = fmt.get('vcodec') not in [None, 'none']
                has_audio = fmt.get('acodec') not in [None, 'none']
                
                if has_video:
                    video_formats.append(format_info)
                elif has_audio:
                    audio_formats.append(format_info)

            # If no formats found, try alternative extraction
            if not video_formats and not audio_formats:
                print("⚠️ No formats found, trying alternative method...")
                return jsonify({
                    'error': 'No downloadable formats found',
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'debug_info': {
                        'formats_count': len(info.get('formats', [])),
                        'age_restricted': info.get('age_limit'),
                        'is_live': info.get('is_live'),
                        'requires_login': info.get('requires_login')
                    }
                }), 404

            # Sort video formats by resolution (best first)
            def get_resolution_rank(format_info):
                res = format_info['resolution']
                resolution_rank = {
                    '4K': 4000, '1440p': 1440, '1080p': 1080, 
                    '720p': 720, '480p': 480, '360p': 360, 
                    '240p': 240, '144p': 144
                }
                return resolution_rank.get(res, 0)
            
            video_formats.sort(key=get_resolution_rank, reverse=True)
            
            response_data = {
                'status': 'success',
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration'),
                'duration_readable': format_duration(info.get('duration')),
                'thumbnail': info.get('thumbnail'),
                'video_formats': video_formats,
                'audio_formats': audio_formats,
                'used_cookies': bool(cookies_path),
                'total_formats': len(video_formats) + len(audio_formats)
            }
            
            return jsonify(response_data)
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Formats error: {error_msg}")
        return jsonify({'error': f'Failed to get formats: {error_msg}'}), 500
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.unlink(cookies_path)
            except:
                pass

@app.route('/download', methods=['POST'])
def download_video():
    """Download specific format"""
    cookies_path = None
    try:
        url = request.json.get('url')
        format_id = request.json.get('format_id')
        
        if not url or not format_id:
            return jsonify({'error': 'URL and format ID required'}), 400

        cookies_path = setup_cookies()

        # Enhanced download options
        ydl_opts = {
            'format': format_id,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_url = info.get('url')
            if not video_url:
                return jsonify({'error': 'Could not extract video URL for selected format'}), 500
            
            # Get selected format details
            selected_format = None
            for fmt in info.get('formats', []):
                if fmt.get('format_id') == format_id:
                    selected_format = fmt
                    break
            
            title = info.get('title', 'video')
            ext = selected_format.get('ext', 'mp4') if selected_format else 'mp4'
            
            clean_title = clean_filename(title)
            filename = f"{clean_title}.{ext}"
            
            response_data = {
                'status': 'success',
                'title': title,
                'filename': filename,
                'download_url': video_url,
                'format': ext.upper(),
                'resolution': selected_format.get('format_note', 'N/A') if selected_format else 'N/A',
                'used_cookies': bool(cookies_path)
            }
            
            return jsonify(response_data)
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Download error: {error_msg}")
        return jsonify({'error': f'Download failed: {error_msg}'}), 500
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.unlink(cookies_path)
            except:
                pass

@app.route('/debug_url', methods=['POST'])
def debug_url():
    """Debug endpoint to see what's happening with a URL"""
    cookies_path = None
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        cookies_path = setup_cookies()

        ydl_opts = {
            'quiet': False,  # Show warnings for debugging
            'no_warnings': False,
            'extract_flat': False,
            'listformats': True,
        }
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            debug_info = {
                'title': info.get('title'),
                'duration': info.get('duration'),
                'formats_count': len(info.get('formats', [])),
                'age_restricted': info.get('age_limit'),
                'is_live': info.get('is_live'),
                'requires_login': info.get('requires_login'),
                'availability': info.get('availability'),
                'formats_preview': []
            }
            
            # Show first 5 formats for preview
            for fmt in info.get('formats', [])[:5]:
                debug_info['formats_preview'].append({
                    'format_id': fmt.get('format_id'),
                    'ext': fmt.get('ext'),
                    'resolution': fmt.get('format_note'),
                    'vcodec': fmt.get('vcodec'),
                    'acodec': fmt.get('acodec'),
                    'url_present': bool(fmt.get('url'))
                })
            
            return jsonify(debug_info)
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.unlink(cookies_path)
            except:
                pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
