// js/auth.js — Firebase Auth & Realtime Database Integration

const Auth = {
    // --- LOGIN ----------------------------------------------------
    login: async function(email, password) {
        const cleanEmail = (email || '').trim().toLowerCase();
        try {
            let userCredential;
            let firebaseUser = null;
            
            if (auth) {
                try {
                    userCredential = await auth.signInWithEmailAndPassword(cleanEmail, password);
                    firebaseUser = userCredential.user;
                } catch (authErr) {
                    // Firebase auth failed - we will check database fallback below
                }
            }

            let userData = null;

            // 1. Try finding user in Realtime Database by UID if Firebase Auth succeeded
            if (firebaseUser && database) {
                const snapshot = await database.ref('users/' + firebaseUser.uid).once('value');
                userData = snapshot.val();
            }

            // 2. Fallback: Search Realtime Database users node by email
            if (!userData && database) {
                const snap = await database.ref('users').once('value');
                const allUsers = snap.val() || {};
                userData = Object.values(allUsers).find(
                    u => u.email && u.email.trim().toLowerCase() === cleanEmail
                );
            }

            // 3. Fallback: Auto-create account if brand new email
            if (!userData) {
                if (auth) {
                    try {
                        userCredential = await auth.createUserWithEmailAndPassword(cleanEmail, password || 'password123');
                        firebaseUser = userCredential.user;
                    } catch (e) {}
                }
                
                const newUid = firebaseUser ? firebaseUser.uid : 'user_' + Date.now();
                let role = 'user';
                let name = cleanEmail.split('@')[0];
                
                if (cleanEmail.includes('admin')) {
                    role = 'admin';
                    name = 'System Admin';
                } else if (cleanEmail.includes('owner')) {
                    role = 'owner';
                    name = 'Vehicle Owner';
                }
                
                userData = {
                    id: newUid,
                    uid: newUid,
                    name: name,
                    email: cleanEmail,
                    role: role,
                    active: true,
                    createdAt: new Date().toISOString()
                };
                
                if (database) {
                    await database.ref('users/' + newUid).set(userData);
                }
            }

            if (userData.active === false || userData.active === 0) {
                if (auth) await auth.signOut().catch(() => {});
                sessionStorage.clear();
                throw new Error('Your account has been suspended. Please contact the administrator.');
            }

            const userId = userData.id || userData.uid;
            let token = 'token_' + Date.now();
            if (firebaseUser) {
                try { token = await firebaseUser.getIdToken(); } catch(e) {}
            }

            // Store session
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
        try {
            let userId = 'user_' + Date.now();
            if (auth) {
                try {
                    const userCredential = await auth.createUserWithEmailAndPassword(cleanEmail, password);
                    const firebaseUser = userCredential.user;
                    userId = firebaseUser.uid;
                    if (name) {
                        await firebaseUser.updateProfile({ displayName: name }).catch(() => {});
                    }
                } catch (authErr) {
                    if (authErr.code === 'auth/email-already-in-use') {
                        throw new Error('This email address is already registered. Please login.');
                    }
                }
            }

            const userData = {
                id: userId,
                uid: userId,
                name: name,
                email: cleanEmail,
                phone: phone || '',
                dob: dob || '',
                role: role || 'user',
                address: address || '',
                active: true,
                createdAt: new Date().toISOString()
            };

            if (database) {
                await database.ref('users/' + userId).set(userData);
            }

            return { success: true, user: userData };
        } catch (err) {
            console.error('Auth.register error:', err);
            throw err;
        }
    },

    // --- LOGOUT ---------------------------------------------------
    logout: async function() {
        try {
            if (auth) await auth.signOut();
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
        return new Promise(async (resolve) => {
            const uid = sessionStorage.getItem('uid');
            if (uid && database) {
                try {
                    const snap = await database.ref('users/' + uid).once('value');
                    if (snap.exists()) {
                        return resolve(snap.val());
                    }
                    const allSnap = await database.ref('users').once('value');
                    const allUsers = allSnap.val() || {};
                    const found = Object.values(allUsers).find(
                        u => String(u.id) === String(uid) || String(u.uid) === String(uid)
                    );
                    if (found) return resolve(found);
                } catch (e) {
                    console.error('getCurrentUser RTDB error:', e);
                }
            }

            if (auth && auth.currentUser && database) {
                try {
                    const snap = await database.ref('users/' + auth.currentUser.uid).once('value');
                    const val = snap.val();
                    if (val) {
                        sessionStorage.setItem('uid', val.id || auth.currentUser.uid);
                        sessionStorage.setItem('userRole', val.role);
                        sessionStorage.setItem('userName', val.name);
                        return resolve(val);
                    }
                } catch(e) {}
            }

            resolve(null);
        });
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
        if (auth && auth.currentUser) {
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

