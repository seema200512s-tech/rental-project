// js/api-config.js
// ─────────────────────────────────────────────────────────────
// Configuration for RentRide Flask REST API Backend URL
// ─────────────────────────────────────────────────────────────

(function() {
    const hostname = window.location.hostname;
    const urlParams = new URLSearchParams(window.location.search);
    const queryApi = urlParams.get('apiUrl');
    const storedApi = localStorage.getItem('RENTRIDE_API_URL');

    if (queryApi) {
        window.RENTRIDE_API_URL = queryApi.replace(/\/+$/, '');
        try { localStorage.setItem('RENTRIDE_API_URL', window.RENTRIDE_API_URL); } catch(e) {}
    } else if (hostname === 'localhost' || hostname === '127.0.0.1') {
        // Force 127.0.0.1 on local development to avoid IPv6 (::1) vs IPv4 binding mismatch on Windows
        const customLocal = storedApi && (storedApi.includes('127.0.0.1') || storedApi.includes('localhost')) ? storedApi : null;
        window.RENTRIDE_API_URL = (customLocal || 'http://127.0.0.1:5000').replace('localhost', '127.0.0.1').replace(/\/+$/, '');
    } else if (hostname === '' || window.location.protocol === 'file:') {
        // Direct file opening via file:///
        window.RENTRIDE_API_URL = 'http://127.0.0.1:5000';
    } else if (hostname.startsWith('192.168.') || hostname.startsWith('10.') || hostname.startsWith('172.')) {
        // Local network testing
        window.RENTRIDE_API_URL = storedApi || `http://${hostname}:5000`;
    } else {
        // Production / Vercel deployment: preserve configured API or fall back to current origin
        window.RENTRIDE_API_URL = storedApi || window.location.origin;
    }
})();
