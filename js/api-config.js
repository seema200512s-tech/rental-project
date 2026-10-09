// js/api-config.js
// ─────────────────────────────────────────────────────────────
// Set window.RENTRIDE_API_URL to your deployed Flask backend URL.
// ─────────────────────────────────────────────────────────────

const hostname = window.location.hostname;

// ⚠️ CHANGE THIS to your main laptop's WiFi IP address (e.g., '192.168.1.5') 
// if you are opening the HTML files directly on another laptop without a web server.
const MAIN_LAPTOP_IP = '127.0.0.1';

if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.startsWith('192.168.') || hostname.startsWith('10.')) {
    window.RENTRIDE_API_URL = `http://${hostname}:5000`;
} else if (hostname === '') {
    // Used when opening files directly via file:///
    window.RENTRIDE_API_URL = `http://${MAIN_LAPTOP_IP}:5000`;
} else {
    // Production URL (Render backend)
    window.RENTRIDE_API_URL = 'https://rentride-api.onrender.com';
}
