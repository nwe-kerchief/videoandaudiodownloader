fetch('/.netlify/functions/proxy', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ /* your data */ })
})
.then(res => res.json())
.then(data => console.log(data));


// DOM Elements
const downloadForm = document.getElementById('downloadForm');
const urlInput = document.getElementById('urlInput');
const pasteBtn = document.getElementById('pasteBtn');
const clearBtn = document.getElementById('clearBtn');
const downloadBtn = document.getElementById('downloadBtn');
const loading = document.getElementById('loading');
const successResult = document.getElementById('successResult');
const errorResult = document.getElementById('errorResult');
const downloadLink = document.getElementById('downloadLink');
const fileInfo = document.getElementById('fileInfo');
const thumbnailPreview = document.getElementById('thumbnailPreview');
const errorMessage = document.getElementById('errorMessage');
const retryBtn = document.getElementById('retryBtn');
const historyList = document.getElementById('historyList');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const clearHistorySection = document.getElementById('clearHistorySection');
const historyCount = document.getElementById('historyCount');

// Progress ring
const progressRing = document.querySelector('.progress-ring-circle');
const circumference = 2 * Math.PI * 36;

// Initialize progress ring
progressRing.style.strokeDasharray = `${circumference} ${circumference}`;
progressRing.style.strokeDashoffset = circumference;

// Download History Management
let downloadHistory = JSON.parse(localStorage.getItem('downloadHistory')) || [];

// Helper function to set progress
function setProgress(percent) {
    const offset = circumference - (percent / 100) * circumference;
    progressRing.style.strokeDashoffset = offset;
}  


(function() {
    'use strict';
    
    const stickyHeader = document.getElementById('stickyHeader');
    const mainHeader = document.getElementById('mainHeader');
    
    function updateStickyHeader() {
        const scrollY = window.pageYOffset || document.documentElement.scrollTop;
        const showSticky = scrollY > 30;
        
        if(showSticky){
            stickyHeader.classList.add('is-visible');
            mainHeader.classList.add('is-compact');
        } else {
            stickyHeader.classList.remove('is-visible');
            mainHeader.classList.remove('is-compact');
        }
    }

    window.addEventListener('scroll', updateStickyHeader, {passive: true});
    updateStickyHeader(); // Initial check
})();



// Render download history
function renderHistory() {
    // Clear expired items (older than 24 hours)
    const now = Date.now();
    downloadHistory = downloadHistory.filter(item => {
        return (now - item.timestamp) < 24 * 60 * 60 * 1000; // 24 hours
    });
    
    localStorage.setItem('downloadHistory', JSON.stringify(downloadHistory));
    
    // Update history count
    historyCount.textContent = downloadHistory.length;
    
    if (downloadHistory.length === 0) {
        historyList.innerHTML = `
            <div class="text-gray-500 text-center py-8 text-sm">
                <i class="fas fa-inbox text-3xl mb-3 opacity-50"></i>
                <div>No recent downloads yet</div>
                <div class="text-xs mt-1">Your download history will appear here</div>
            </div>
        `;
        clearHistorySection.classList.add('hidden');
        return;
    }
    
    clearHistorySection.classList.remove('hidden');
    
    historyList.innerHTML = downloadHistory.map(item => `
        <div class="history-item bg-gray-50 rounded-xl p-4 border border-gray-100">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="history-item-content flex items-center space-x-3 md:space-x-4 flex-1 min-w-0">
                    <div class="w-10 h-10 md:w-12 md:h-12 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center text-white flex-shrink-0">
                        <i class="fas fa-${item.format === 'mp3' ? 'music' : 'film'} text-sm md:text-base"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="text-gray-800 font-semibold text-xs md:text-sm truncate-2-lines">${item.title}</div>
                        <div class="text-gray-500 text-xs flex items-center flex-wrap gap-1 md:gap-2 mt-1">
                            <span class="bg-${getPlatformColor(item.platform)}-100 text-${getPlatformColor(item.platform)}-600 px-2 py-0.5 rounded-full capitalize text-xs">${item.platform}</span>
                            <span>•</span>
                            <span>${item.format.toUpperCase()}</span>
                            <span>•</span>
                            <span>${item.size_mb}MB</span>
                        </div>
                    </div>
                </div>
                <div class="history-item-buttons flex gap-2 flex-shrink-0">
                    <button onclick="redownloadItem('${item.download_url}', '${item.title}', '${item.format}')" 
                            class="flex-1 sm:flex-initial px-3 py-2 bg-green-500 hover:bg-green-600 text-white text-xs font-semibold rounded-lg transition-all duration-300 flex items-center justify-center gap-1"
                            title="Download Again">
                        <i class="fas fa-download text-xs"></i>
                        <span>Download</span>
                    </button>
                    <button onclick="removeFromHistory('${item.id}')" 
                            class="w-8 h-8 bg-red-500/10 hover:bg-red-500/20 rounded-lg flex items-center justify-center text-red-500 transition-colors flex-shrink-0"
                            title="Remove from History">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

// Helper function to get platform color
function getPlatformColor(platform) {
    const colors = {
        'youtube': 'red',
        'tiktok': 'pink',
        'facebook': 'blue'
    };
    return colors[platform] || 'gray';
}

// Add item to history
function addToHistory(data) {
    const historyItem = {
        id: Date.now().toString(),
        timestamp: Date.now(),
        ...data
    };
    
    // Remove if already exists (prevent duplicates)
    downloadHistory = downloadHistory.filter(item => item.download_url !== data.download_url);
    
    // Add to beginning of array
    downloadHistory.unshift(historyItem);
    
    // Keep only last 10 items
    if (downloadHistory.length > 10) {
        downloadHistory = downloadHistory.slice(0, 10);
    }
    
    localStorage.setItem('downloadHistory', JSON.stringify(downloadHistory));
    renderHistory();
}

// Remove item from history
function removeFromHistory(id) {
    downloadHistory = downloadHistory.filter(item => item.id !== id);
    localStorage.setItem('downloadHistory', JSON.stringify(downloadHistory));
    renderHistory();
}

// Clear all history
function clearAllHistory() {
    if (confirm('Are you sure you want to clear all download history?')) {
        downloadHistory = [];
        localStorage.setItem('downloadHistory', JSON.stringify(downloadHistory));
        renderHistory();
    }
}

// Redownload item
function redownloadItem(url, title, format) {
    // Create a temporary download link
    const link = document.createElement('a');
    link.href = url;
    link.download = `${title}.${format}`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Paste from clipboard
pasteBtn.addEventListener('click', async () => {
    try {
        const text = await navigator.clipboard.readText();
        urlInput.value = text;
        urlInput.focus();
        
        // Show success feedback
        const originalText = pasteBtn.innerHTML;
        pasteBtn.innerHTML = '<i class="fas fa-check"></i> <span class="hidden sm:inline">Pasted!</span><span class="sm:hidden">✓</span>';
        pasteBtn.classList.remove('from-purple-500', 'to-purple-600');
        pasteBtn.classList.add('from-green-500', 'to-green-600');
        
        setTimeout(() => {
            pasteBtn.innerHTML = originalText;
            pasteBtn.classList.remove('from-green-500', 'to-green-600');
            pasteBtn.classList.add('from-purple-500', 'to-purple-600');
        }, 2000);
    } catch (err) {
        alert('Unable to paste from clipboard. Please paste manually.');
    }
});

// Clear form
clearBtn.addEventListener('click', () => {
    urlInput.value = '';
    urlInput.focus();
    resetForm();
});

// Clear history
clearHistoryBtn.addEventListener('click', clearAllHistory);

// Form submission
downloadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const url = urlInput.value.trim();
    const format = document.querySelector('input[name="format"]:checked').value;
    
    if (!url) {
        showError('Please enter a valid URL');
        return;
    }
    
    // Validate URL
    if (!isValidUrl(url)) {
        showError('Please enter a valid YouTube or TikTok URL');
        return;
    }
    
    // Start download process
    startDownload(url, format);
});

// Helper function to validate URLs
function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.hostname.includes('youtube.com') || 
               url.hostname.includes('youtu.be') || 
               url.hostname.includes('tiktok.com') ||
               url.hostname.includes('facebook.com');
    } catch (_) {
        return false;
    }
}

// Start download process
async function startDownload(url, format) {
    // Reset UI
    resetUI();
    showLoading();
    
    try {
        // Update progress
        setProgress(30);
        
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: url,
                format: format
            })
        });
        
        // Update progress
        setProgress(70);
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Server error');
        }
        
        if (data.success) {
            // Complete progress
            setProgress(100);
            
            // Add to history
            addToHistory(data);
            
            // Simulate processing delay for better UX
            setTimeout(() => {
                showSuccess(data, url);
            }, 1000);
        } else {
            throw new Error(data.error || 'Download failed');
        }
        
    } catch (error) {
        showError(error.message);
    }
}

// UI Functions
function resetUI() {
    successResult.classList.add('hidden');
    errorResult.classList.add('hidden');
    loading.classList.add('hidden');
    downloadBtn.disabled = false;
    
    // Reset progress
    setProgress(0);
}

function resetForm() {
    resetUI();
    urlInput.value = ''; // Clear input for next download
    urlInput.focus();
}

function showLoading() {
    downloadBtn.disabled = true;
    loading.classList.remove('hidden');
    successResult.classList.add('hidden');
    errorResult.classList.add('hidden');
    
    // Show loading thumbnail
    thumbnailPreview.innerHTML = `
        <div class="w-full h-full thumbnail-loading rounded-lg flex items-center justify-center">
            <div class="text-center text-gray-500">
                <i class="fas fa-spinner fa-spin text-2xl mb-2"></i>
                <div class="text-sm">Loading thumbnail...</div>
            </div>
        </div>
    `;
    
    // Animate progress steps
    const steps = document.querySelectorAll('.loading-step');
    steps.forEach((step, index) => {
        setTimeout(() => {
            step.classList.remove('opacity-50');
            step.querySelector('.step-icon').classList.remove('bg-gray-100');
            step.querySelector('.step-icon').classList.add('bg-purple-100');
            step.querySelector('.step-text').classList.remove('text-gray-500');
            step.querySelector('.step-text').classList.add('text-purple-600');
        }, index * 1000);
    });
}

function showSuccess(data, originalUrl) {
    loading.classList.add('hidden');
    successResult.classList.remove('hidden');
    
    // Clear input for next download
    urlInput.value = '';
    
    // Use the actual video title from API or fallback
    const videoTitle = data.title || 'Video Download';
    const displayFilename = data.filename || `download.${data.format}`;
    
    // Generate and display thumbnail (simple approach from second file)
    const thumbnailUrl = generateYouTubeThumbnail(originalUrl);
    if (thumbnailUrl) {
        thumbnailPreview.innerHTML = `
            <img src="${thumbnailUrl}" alt="${videoTitle}" class="w-full h-full object-cover rounded-lg" 
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">
            <div class="hidden w-full h-full bg-gray-100 rounded-lg flex items-center justify-center">
                <div class="text-center text-gray-500 p-4">
                    <i class="fas fa-file-${data.format === 'mp3' ? 'audio' : 'video'} text-4xl mb-2"></i>
                    <div class="font-semibold text-sm">${videoTitle}</div>
                </div>
            </div>
        `;
    } else {
        thumbnailPreview.innerHTML = `
            <div class="text-center text-gray-500 p-4">
                <i class="fas fa-file-${data.format === 'mp3' ? 'audio' : 'video'} text-4xl md:text-6xl mb-4"></i>
                <div class="font-semibold text-base md:text-lg">${videoTitle}</div>
                <div class="text-xs md:text-sm mt-2 text-gray-400">${data.format.toUpperCase()} File</div>
            </div>
        `;
    }
    
    // Create file info
    fileInfo.innerHTML = `
        <div class="flex justify-between items-center py-2 border-b border-gray-100">
            <span class="font-medium text-gray-600 text-xs md:text-sm">File Name:</span>
            <span class="font-semibold text-gray-800 truncate ml-2 text-xs md:text-sm max-w-[60%]">${videoTitle}</span>
        </div>
        <div class="flex justify-between items-center py-2 border-b border-gray-100">
            <span class="font-medium text-gray-600 text-xs md:text-sm">File Size:</span>
            <span class="font-semibold text-blue-600 text-xs md:text-sm">${data.size_mb || 'Unknown'} MB</span>
        </div>
        <div class="flex justify-between items-center py-2 border-b border-gray-100">
            <span class="font-medium text-gray-600 text-xs md:text-sm">Format:</span>
            <span class="font-semibold text-purple-600 text-xs md:text-sm">${data.format.toUpperCase()}</span>
        </div>
        <div class="flex justify-between items-center py-2">
            <span class="font-medium text-gray-600 text-xs md:text-sm">Platform:</span>
            <span class="font-semibold text-green-600 capitalize text-xs md:text-sm">${data.platform || 'Unknown'}</span>
        </div>
    `;
    
    // Set download attribute with proper filename
    const cleanTitle = videoTitle.replace(/[<>:"/\\|?*]/g, '').substring(0, 100);
    // Set download link
    downloadLink.href = data.download_url;
    downloadLink.setAttribute('download', `${cleanTitle}.${data.format}`);
    downloadLink.setAttribute('target', '_blank');
    
    // Remove any existing click handlers and add direct download
    downloadLink.onclick = function(e) {
        // Let the browser handle the download naturally
        // The download attribute should force download instead of playing
        return true;
    };
    
    // Update button text to be clearer
    downloadLink.innerHTML = '<i class="fas fa-download"></i> Download File Now';
    
    // Scroll to result
    successResult.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Generate simple YouTube thumbnail URL (from second file)
function generateYouTubeThumbnail(url) {
    try {
        const urlObj = new URL(url);
        let videoId;
        
        if (urlObj.hostname.includes('youtu.be')) {
            videoId = urlObj.pathname.slice(1);
        } else if (urlObj.hostname.includes('youtube.com')) {
            videoId = urlObj.searchParams.get('v');
        }
        
        if (videoId) {
            return `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
        }
    } catch (e) {
        console.error('Error generating YouTube thumbnail:', e);
    }
    return null;
}

function showError(message) {
    loading.classList.add('hidden');
    errorResult.classList.remove('hidden');
    errorMessage.textContent = message;
    
    // Scroll to error
    errorResult.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Event listeners for buttons
retryBtn.addEventListener('click', () => {
    const url = urlInput.value;
    const format = document.querySelector('input[name="format"]:checked').value;
    startDownload(url, format);
});

// URL validation on input
urlInput.addEventListener('input', function() {
    const url = this.value.trim();
    if (url && isValidUrl(url)) {
        this.classList.remove('border-gray-200');
        this.classList.add('border-green-500', 'ring-2', 'ring-green-200');
    } else if (url) {
        this.classList.remove('border-gray-200');
        this.classList.add('border-red-500', 'ring-2', 'ring-red-200');
    } else {
        this.classList.remove('border-green-500', 'border-red-500', 'ring-2', 'ring-green-200', 'ring-red-200');
        this.classList.add('border-gray-200');
    }
});

// Format selection styling
document.querySelectorAll('.format-option input').forEach(radio => {
    radio.addEventListener('change', function() {
        document.querySelectorAll('.format-label').forEach(label => {
            label.classList.remove('border-purple-400', 'bg-purple-50', 'border-green-400', 'bg-green-50');
        });
        
        const selectedLabel = this.nextElementSibling;
        if (this.value === 'mp4') {
            selectedLabel.classList.add('border-purple-400', 'bg-purple-50');
        } else {
            selectedLabel.classList.add('border-green-400', 'bg-green-50');
        }
    });
});

// Initialize format selection
document.querySelector('#format-mp4').dispatchEvent(new Event('change'));

// Initialize history
renderHistory();

// Initialize

resetUI();


