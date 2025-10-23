from flask import Flask, request, jsonify, render_template, send_file
import yt_dlp
import re
import os
import tempfile
import base64
import threading
import time
import random
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Store download jobs
download_jobs = {}
JOB_TIMEOUT = 300  # 5 minutes

def clean_filename(filename):
    return re.sub(r'[^\w\s-]', '', filename).strip()

def setup_cookies():
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
    if not bytes_size:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def get_user_agent():
    """Return random user agent to avoid detection"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    return random.choice(user_agents)

def download_video_worker(job_id, url, format_id, download_dir):
    """Background worker to download video with enhanced options"""
    try:
        cookies_path = setup_cookies()
        
        # Enhanced yt-dlp options for better YouTube compatibility
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'quiet': False,  # Show output for debugging
            'no_warnings': False,
            
            # Enhanced options for YouTube
            'ignoreerrors': True,
            'no_check_certificate': True,
            'prefer_insecure': False,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'keep_fragments': True,
            
            # Throttling handling
            'throttled_rate': '100K',
            'buffersize': 1024 * 32,
            'http_chunk_size': 10485760,
            
            # Headers and user agent
            'user_agent': get_user_agent(),
            'http_headers': {
                'User-Agent': get_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Connection': 'keep-alive',
            },
        }
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path
            print("🔑 Using cookies for authentication")

        print(f"🎯 Starting download with options: {ydl_opts['format']}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Verify file was actually downloaded
            if not os.path.exists(filename):
                raise Exception("Download completed but file not found")
                
            file_size = os.path.getsize(filename)
            if file_size == 0:
                raise Exception("Download completed but file is empty")
            
            download_jobs[job_id].update({
                'status': 'completed',
                'filename': filename,
                'title': info.get('title', 'video'),
                'filesize': file_size,
                'completed_at': time.time()
            })
            print(f"✅ Download completed successfully: {file_size} bytes")
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Download error: {error_msg}")
        download_jobs[job_id].update({
            'status': 'error',
            'error': error_msg
        })
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.unlink(cookies_path)
            except:
                pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_formats', methods=['POST'])
def get_formats():
    cookies_path = None
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        print(f"🔍 Processing URL: {url}")
        cookies_path = setup_cookies()

        # Enhanced format extraction
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            'user_agent': get_user_agent(),
        }
        
        if cookies_path:
            ydl_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get available formats
            video_formats = []
            audio_formats = []
            
            for fmt in info.get('formats', []):
                # Skip formats that are obviously throttled or problematic
                format_note = fmt.get('format_note', '')
                if 'throttled' in format_note.lower():
                    continue  # Skip throttled formats
                    
                format_info = {
                    'format_id': fmt.get('format_id'),
                    'ext': fmt.get('ext', 'unknown'),
                    'resolution': fmt.get('format_note', 'Unknown'),
                    'filesize': fmt.get('filesize'),
                    'filesize_readable': format_size(fmt.get('filesize')),
                    'vcodec': fmt.get('vcodec', 'none'),
                    'acodec': fmt.get('acodec', 'none'),
                    'quality': fmt.get('quality', 0),
                }
                
                if fmt.get('vcodec') != 'none':
                    video_formats.append(format_info)
                elif fmt.get('acodec') != 'none':
                    audio_formats.append(format_info)

            # If no good formats found, try to get at least one
            if not video_formats and info.get('formats'):
                for fmt in info.get('formats', []):
                    if fmt.get('vcodec') != 'none' and fmt.get('url'):
                        format_info = {
                            'format_id': fmt.get('format_id'),
                            'ext': fmt.get('ext', 'unknown'),
                            'resolution': fmt.get('format_note', 'Unknown'),
                            'filesize': fmt.get('filesize'),
                            'filesize_readable': format_size(fmt.get('filesize')),
                            'vcodec': fmt.get('vcodec', 'none'),
                            'acodec': fmt.get('acodec', 'none'),
                        }
                        video_formats.append(format_info)
                        break

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

@app.route('/start_download', methods=['POST'])
def start_download():
    """Start a background download with enhanced format selection"""
    try:
        url = request.json.get('url')
        format_id = request.json.get('format_id')
        
        if not url or not format_id:
            return jsonify({'error': 'URL and format ID required'}), 400

        # Create job
        job_id = f"job_{int(time.time())}_{os.urandom(4).hex()}"
        download_dir = tempfile.mkdtemp()
        
        download_jobs[job_id] = {
            'status': 'downloading',
            'url': url,
            'format_id': format_id,
            'download_dir': download_dir,
            'started_at': time.time(),
            'progress': 0
        }
        
        # Start background download
        thread = threading.Thread(
            target=download_video_worker,
            args=(job_id, url, format_id, download_dir)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'started',
            'job_id': job_id,
            'message': 'Download started in background'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to start download: {str(e)}'}), 500

@app.route('/check_download/<job_id>')
def check_download(job_id):
    """Check download status"""
    job = download_jobs.get(job_id)
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    # Clean up old jobs
    if time.time() - job.get('started_at', 0) > JOB_TIMEOUT:
        # Clean up files
        if 'filename' in job and os.path.exists(job['filename']):
            try:
                os.remove(job['filename'])
            except:
                pass
        if 'download_dir' in job and os.path.exists(job['download_dir']):
            try:
                os.rmdir(job['download_dir'])
            except:
                pass
        del download_jobs[job_id]
        return jsonify({'error': 'Job expired'}), 404
    
    response = {
        'status': job['status'],
        'job_id': job_id
    }
    
    if job['status'] == 'completed':
        response.update({
            'filename': job['filename'],
            'title': job['title'],
            'filesize': job['filesize'],
            'download_url': f'/download_file/{job_id}'
        })
    elif job['status'] == 'error':
        response['error'] = job['error']
    
    return jsonify(response)

@app.route('/download_file/<job_id>')
def download_file(job_id):
    """Serve the downloaded file"""
    job = download_jobs.get(job_id)
    
    if not job or job['status'] != 'completed':
        return jsonify({'error': 'File not available'}), 404
    
    try:
        filename = job['filename']
        safe_filename = secure_filename(os.path.basename(filename))
        
        response = send_file(
            filename,
            as_attachment=True,
            download_name=safe_filename
        )
        
        # Schedule cleanup after download
        def cleanup_file():
            time.sleep(10)  # Wait 10 seconds before cleanup
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                if 'download_dir' in job and os.path.exists(job['download_dir']):
                    os.rmdir(job['download_dir'])
                if job_id in download_jobs:
                    del download_jobs[job_id]
            except:
                pass
        
        cleanup_thread = threading.Thread(target=cleanup_file)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        return response
        
    except Exception as e:
        return jsonify({'error': f'Failed to serve file: {str(e)}'}), 500

@app.route('/direct_download', methods=['POST'])
def direct_download():
    """Alternative download method that tries different approaches"""
    cookies_path = None
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        cookies_path = setup_cookies()
        download_dir = tempfile.mkdtemp()
        
        # Try different format strategies
        format_strategies = [
            'best[height<=720]',  # Try 720p or lower first
            'best[ext=mp4]',      # Then try any MP4
            'best',               # Then try anything
            'worst',              # Finally try worst quality (often less restricted)
        ]
        
        for strategy in format_strategies:
            try:
                ydl_opts = {
                    'format': strategy,
                    'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                    'quiet': False,
                    'no_warnings': False,
                    'ignoreerrors': True,
                    'retries': 3,
                    'user_agent': get_user_agent(),
                }
                
                if cookies_path:
                    ydl_opts['cookiefile'] = cookies_path
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    if os.path.exists(filename) and os.path.getsize(filename) > 0:
                        safe_filename = secure_filename(os.path.basename(filename))
                        return send_file(filename, as_attachment=True, download_name=safe_filename)
                        
            except Exception as e:
                print(f"❌ Strategy {strategy} failed: {e}")
                continue
        
        return jsonify({'error': 'All download strategies failed'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Direct download failed: {str(e)}'}), 500
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.unlink(cookies_path)
            except:
                pass

# Cleanup old jobs periodically
def cleanup_old_jobs():
    while True:
        try:
            current_time = time.time()
            expired_jobs = [
                job_id for job_id, job in download_jobs.items()
                if current_time - job.get('started_at', 0) > JOB_TIMEOUT
            ]
            for job_id in expired_jobs:
                # Clean up files
                job = download_jobs[job_id]
                if 'filename' in job and os.path.exists(job['filename']):
                    try:
                        os.remove(job['filename'])
                    except:
                        pass
                if 'download_dir' in job and os.path.exists(job['download_dir']):
                    try:
                        os.rmdir(job['download_dir'])
                    except:
                        pass
                del download_jobs[job_id]
        except:
            pass
        time.sleep(60)  # Check every minute

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_jobs)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
