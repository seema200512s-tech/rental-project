// js/api-config.js
// ─────────────────────────────────────────────────────────────
// Configuration for RentRide Flask REST API Backend URL
// ─────────────────────────────────────────────────────────────

(function() {
    const hostname = window.location.hostname;
    const urlParams = new URLSearchParams(window.location.search);
    const customApi = urlParams.get('apiUrl') || localStorage.getItem('RENTRIDE_API_URL');

    if (customApi) {
        window.RENTRIDE_API_URL = customApi.replace(/\/+$/, '');
    } else if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.startsWith('192.168.') || hostname.startsWith('10.')) {
        window.RENTRIDE_API_URL = `http://${hostname || '127.0.0.1'}:5000`;
    } else if (hostname === '') {
        // Used when opening files directly via file:///
        window.RENTRIDE_API_URL = 'http://127.0.0.1:5000';
    } else {
        // Default to same origin / local fallback if proxying, or configured backend host
        window.RENTRIDE_API_URL = window.location.origin.includes('vercel.app')
            ? (localStorage.getItem('RENTRIDE_API_URL') || `http://127.0.0.1:5000`)
            : `${window.location.protocol}//${hostname}:5000`;
    }
})();
