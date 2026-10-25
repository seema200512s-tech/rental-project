// js/auth.js — Authentication with Firebase Auth & MySQL Backend
// ─────────────────────────────────────────────────────────────

const Auth = {
    // --- LOGIN ----------------------------------------------------
    login: async function(email, password) {
        const cleanEmail = (email || '').trim().toLowerCase();
        if (!cleanEmail || !password) {
            throw new Error('Please enter both email and password.');
        }

        try {
            let firebaseUser = null;
            let firebaseError = null;

            // 1. Try Firebase Authentication
            if (typeof auth !== 'undefined' && auth) {
                try {
                    const userCredential = await auth.signInWithEmailAndPassword(cleanEmail, password);
                    firebaseUser = userCredential.user;
                } catch (authErr) {
                    firebaseError = authErr;
                    console.warn('Firebase Auth notice:', authErr.code || authErr.message);
                }
            }

            let userData = null;
            let token = null;

            // 2. Synchronize session with Flask REST API
            const apiUrl = window.RENTRIDE_API_URL || 'http://127.0.0.1:5000';

            if (firebaseUser) {
                // Exchange Firebase UID with backend
                const sessionRes = await fetch(apiUrl + '/api/auth/session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        uid: firebaseUser.uid,
                        email: cleanEmail
                    })
                });

                if (sessionRes.ok) {
                    const sessionData = await sessionRes.json();
                    userData = sessionData.user;
                    token = sessionData.token;
                } else if (sessionRes.status === 403) {
                    const errData = await sessionRes.json().catch(() => ({}));
                    if (auth) await auth.signOut().catch(() => {});
                    sessionStorage.clear();
                    throw new Error(errData.error || 'Your account has been suspended. Please contact administrator.');
                }
            }

            // 3. Fallback: Authenticate directly against backend MySQL if Firebase Auth failed or account exists locally
            if (!userData) {
                const loginRes = await fetch(apiUrl + '/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: cleanEmail,
                        password: password
                    })
                });

                if (loginRes.ok) {
                    const loginData = await loginRes.json();
                    userData = loginData.user;
                    token = loginData.token;
                } else {
                    const errData = await loginRes.json().catch(() => ({}));
                    if (loginRes.status === 403) {
                        throw new Error(errData.error || 'Your account has been suspended.');
                    }
                    if (firebaseError && firebaseError.code === 'auth/wrong-password') {
                        throw new Error('Incorrect password. Please try again.');
                    }
                    if (firebaseError && firebaseError.code === 'auth/user-not-found') {
                        throw new Error('No account found with this email. Please register first.');
                    }
                    throw new Error(errData.error || 'Invalid email or password.');
                }
            }

            if (!userData || !token) {
                throw new Error('Authentication failed. Please verify your credentials.');
            }

            if (userData.active === false || userData.active === 0) {
                if (auth) await auth.signOut().catch(() => {});
                sessionStorage.clear();
                throw new Error('Your account has been suspended. Please contact the administrator.');
            }

            // Store session
            const userId = userData.id || userData.uid;
            sessionStorage.setItem('token', token);
            sessionStorage.setItem('uid', userId);
            sessionStorage.setItem('userRole', userData.role);
            sessionStorage.setItem('userName', userData.name);

            return userData;
        } catch (err) {
            console.error('Auth.login error:', err);
            throw err;
        }
    },

    // --- REGISTER -------------------------------------------------
    register: async function(name, email, phone, dob, password, role, address) {
        const cleanEmail = (email || '').trim().toLowerCase();
        const cleanRole = (role || 'user').trim().toLowerCase();

        if (cleanRole !== 'user' && cleanRole !== 'owner') {
            throw new Error('Invalid account role.');
        }

        if (dob && !Auth.checkAge18(dob)) {
            throw new Error('You must be at least 18 years old to register.');
        }

        try {
            let firebaseUid = null;

            // 1. Create account in Firebase Authentication
            if (typeof auth !== 'undefined' && auth) {
                try {
                    const userCredential = await auth.createUserWithEmailAndPassword(cleanEmail, password);
                    const firebaseUser = userCredential.user;
                    firebaseUid = firebaseUser.uid;
                    if (name) {
                        await firebaseUser.updateProfile({ displayName: name }).catch(() => {});
                    }
                } catch (authErr) {
                    if (authErr.code === 'auth/email-already-in-use') {
                        throw new Error('This email address is already registered. Please login.');
                    } else if (authErr.code === 'auth/weak-password') {
                        throw new Error('Password must be at least 6 characters.');
                    } else if (authErr.code === 'auth/invalid-email') {
                        throw new Error('Please enter a valid email address.');
                    } else {
                        console.warn('Firebase createUser notice:', authErr);
                    }
                }
            }

            // 2. Synchronize user record with MySQL backend
            const apiUrl = window.RENTRIDE_API_URL || 'http://127.0.0.1:5000';
            const res = await fetch(apiUrl + '/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    uid: firebaseUid,
                    name: name,
                    email: cleanEmail,
                    phone: phone || '',
                    dob: dob || null,
                    address: address || '',
                    role: cleanRole,
                    password: password
                })
            });

            const resData = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(resData.error || 'Failed to complete registration.');
            }

            return { success: true, uid: resData.uid || firebaseUid };
        } catch (err) {
            console.error('Auth.register error:', err);
            throw err;
        }
    },

    // --- LOGOUT ---------------------------------------------------
    logout: async function() {
        try {
            if (typeof auth !== 'undefined' && auth) {
                await auth.signOut().catch(() => {});
            }
        } catch (e) {
            console.error('Error signing out:', e);
        }
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

        if (!token && !uid) {
            return null;
        }

        const apiUrl = window.RENTRIDE_API_URL || 'http://127.0.0.1:5000';

        // Validate session with backend
        if (token) {
            try {
                const res = await fetch(apiUrl + '/api/auth/me', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (res.ok) {
                    const data = await res.json();
                    const user = data.user;
                    sessionStorage.setItem('uid', user.id);
                    sessionStorage.setItem('userRole', user.role);
                    sessionStorage.setItem('userName', user.name);
                    return user;
                }
            } catch (e) {
                // If offline / network error, fallback to session storage values
                const fallbackRole = sessionStorage.getItem('userRole');
                const fallbackName = sessionStorage.getItem('userName');
                if (fallbackRole && uid) {
                    return { id: uid, uid: uid, role: fallbackRole, name: fallbackName, active: true };
                }
            }
        }

        // Try restoring from Firebase Auth currentUser
        if (typeof auth !== 'undefined' && auth && auth.currentUser) {
            try {
                const sessionRes = await fetch(apiUrl + '/api/auth/session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ uid: auth.currentUser.uid, email: auth.currentUser.email })
                });
                if (sessionRes.ok) {
                    const sessionData = await sessionRes.json();
                    sessionStorage.setItem('token', sessionData.token);
                    sessionStorage.setItem('uid', sessionData.user.id);
                    sessionStorage.setItem('userRole', sessionData.user.role);
                    sessionStorage.setItem('userName', sessionData.user.name);
                    return sessionData.user;
                }
            } catch (e) {}
        }

        return null;
    },

    // --- ROLE GUARD -----------------------------------------------
    requireRole: async function(requiredRole) {
        const userData = await Auth.getCurrentUser();
        
        if (!userData) {
            alert('Session expired or not logged in. Please login to continue.');
            Auth._redirectToLogin();
            return null;
        }

        if (userData.active === false || userData.active === 0) {
            alert('Your account has been suspended. Contact the administrator.');
            sessionStorage.clear();
            Auth._redirectToLogin();
            return null;
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
            return null;
        }

        return userData;
    },

    updatePassword: async function(newPassword) {
        if (typeof auth !== 'undefined' && auth && auth.currentUser) {
            await auth.currentUser.updatePassword(newPassword);
        }
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
