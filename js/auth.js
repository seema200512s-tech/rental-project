// js/auth.js — Flask REST API Authentication + Role-Based Access Control

const API_BASE_URL = 'http://127.0.0.1:5000/api';

const Auth = {
    // --- LOGIN ----------------------------------------------------
    login: async function(email, password) {
        try {
            const response = await fetch(`${API_BASE_URL}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Login failed');
            }
            
            const { token, user } = data;
            
            // Store token and role in session for quick access
            sessionStorage.setItem('token', token);
            sessionStorage.setItem('uid', user.id);
            sessionStorage.setItem('userRole', user.role);
            sessionStorage.setItem('userName', user.name);
            
            return user;
        } catch (err) {
            throw err;
        }
    },

    // --- REGISTER -------------------------------------------------
    register: async function(name, email, phone, dob, password, role, address) {
        try {
            const response = await fetch(`${API_BASE_URL}/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, phone, dob, password, role, address })
            });
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Registration failed');
            }
            
            return { success: true };
        } catch (err) {
            throw err;
        }
    },

    // --- LOGOUT ---------------------------------------------------
    logout: function() {
        sessionStorage.clear();
        Auth._redirectToLogin();
        return Promise.resolve();
    },

    // --- HELPER: redirect to login --------------------------------
    _redirectToLogin: function() {
        const p = window.location.pathname;
        const isNested = p.includes('/admin/') || p.includes('/owner/') || p.includes('/user/');
        window.location.href = isNested ? '../login.html' : 'login.html';
    },

    // --- GET CURRENT USER -----------------------------------------
    getCurrentUser: async function() {
        const token = sessionStorage.getItem('token');
        const uid = sessionStorage.getItem('uid');
        if (!token || !uid) return null;
        
        try {
            const response = await fetch(`${API_BASE_URL}/users/${uid}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                return await response.json();
            }
            return null;
        } catch (err) {
            console.error('Auth.getCurrentUser error', err);
            return null;
        }
    },

    // --- ROLE GUARD -----------------------------------------------
    requireRole: async function(requiredRole) {
        const token = sessionStorage.getItem('token');
        const uid = sessionStorage.getItem('uid');
        
        if (!token || !uid) {
            alert('Session expired. Please login to continue.');
            Auth._redirectToLogin();
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/users/${uid}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (!response.ok) {
                alert('Session invalid. Please login again.');
                sessionStorage.clear();
                Auth._redirectToLogin();
                return;
            }
            
            const userData = await response.json();
            
            if (userData.active === false || userData.active === 0) {
                alert('Your account has been suspended. Contact the administrator.');
                sessionStorage.clear();
                Auth._redirectToLogin();
                return;
            }

            if (userData.role !== requiredRole) {
                alert('Access denied. You do not have permission to view this page.');
                const roleMap = {
                    admin: 'admin/dashboard.html',
                    owner: 'owner/dashboard.html',
                    user:  'user/dashboard.html'
                };
                const p = window.location.pathname;
                const isNested = p.includes('/admin/') || p.includes('/owner/') || p.includes('/user/');
                const prefix = isNested ? '../' : '';
                const target = roleMap[userData.role];

                if (target) {
                    window.location.href = prefix + target;
                } else {
                    sessionStorage.clear();
                    Auth._redirectToLogin();
                }
                return;
            }

            return userData;
        } catch (err) {
            console.error('Auth.requireRole error', err);
            alert('Unable to verify your account. Please login again.');
            sessionStorage.clear();
            Auth._redirectToLogin();
        }
    },

    updatePassword: function(newPassword) {
        // Mock update for now
        return Promise.resolve();
    },

    checkAge18: function(dob) {
        if (!dob) return false;
        const dobDate = new Date(dob);
        const today = new Date();
        let age = today.getFullYear() - dobDate.getFullYear();
        const m = today.getMonth() - dobDate.getMonth();
        if (m < 0 || (m === 0 && today.getDate() < dobDate.getDate())) age--;
        return age >= 18;
    },

    maskAadhaar: function(aadhaarNumber) {
        if (!aadhaarNumber || aadhaarNumber.length < 4) return 'XXXX XXXX XXXX';
        return 'XXXX XXXX ' + aadhaarNumber.slice(-4);
    },

    maskLicense: function(licenseNumber) {
        if (!licenseNumber || licenseNumber.length < 4) return '****';
        return '****' + licenseNumber.slice(-4);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.logout-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            if (confirm('Are you sure you want to logout?')) {
                Auth.logout();
            }
        });
    });
});
