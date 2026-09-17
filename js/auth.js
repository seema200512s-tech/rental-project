// js/auth.js — Firebase Authentication + Role-Based Access Control
// Requires firebase-config.js and db.js to be loaded first.

const Auth = {

    // --- LOGIN ----------------------------------------------------
    login: function(email, password) {
        return auth.signInWithEmailAndPassword(email, password)
            .then(async (cred) => {
                let userData;
                try {
                    userData = await DB.getUser(cred.user.uid);
                } catch (dbErr) {
                    await auth.signOut();
                    throw new Error('Unable to read account data. Please try again.');
                }
                // Case 1: Auth OK but no DB profile
                if (!userData) {
                    await auth.signOut();
                    throw new Error('Account profile not found. Please register or contact support.');
                }
                // Case 2: Role field missing
                if (!userData.role) {
                    await auth.signOut();
                    throw new Error('Account has no role assigned. Contact the administrator.');
                }
                // Suspended account
                if (userData.active === false || userData.status === 'Suspended') {
                    await auth.signOut();
                    throw new Error('Your account has been suspended. Contact the administrator.');
                }
                // Store role in session for quick access
                sessionStorage.setItem('uid', cred.user.uid);
                sessionStorage.setItem('userRole', userData.role);
                sessionStorage.setItem('userName', userData.name);
                return userData;
            });
    },

    // --- REGISTER -------------------------------------------------
    register: function(name, email, phone, dob, password, role, address) {
        return auth.createUserWithEmailAndPassword(email, password)
            .then(async (cred) => {
                const profileData = {
                    name: name,
                    email: email,
                    phone: phone,
                    dob: dob,
                    address: address || '',
                    role: role,       // "user" or "owner" — never "admin" from the form
                    active: true,
                    createdAt: new Date().toISOString()
                };
                await DB.setUser(cred.user.uid, profileData);
                await auth.signOut(); // Must login explicitly after registration
                return { success: true };
            });
    },

    // --- LOGOUT ---------------------------------------------------
    logout: function() {
        sessionStorage.clear();
        return auth.signOut().then(() => {
            Auth._redirectToLogin();
        });
    },

    // --- HELPER: redirect to login --------------------------------
    _redirectToLogin: function() {
        const p = window.location.pathname;
        const isNested = p.includes('/admin/') || p.includes('/owner/') || p.includes('/user/');
        window.location.href = isNested ? '../login.html' : 'login.html';
    },

    // --- GET CURRENT USER -----------------------------------------
    getCurrentUser: function() {
        return new Promise((resolve) => {
            const unsub = auth.onAuthStateChanged(async (user) => {
                unsub(); // detach immediately — one-shot
                if (!user) { resolve(null); return; }
                try {
                    const userData = await DB.getUser(user.uid);
                    resolve(userData ? { uid: user.uid, ...userData } : null);
                } catch (err) {
                    console.error('Auth.getCurrentUser: DB read failed', err);
                    resolve(null);
                }
            });
        });
    },

    // --- ROLE GUARD -----------------------------------------------
    // Call at the top of every protected page.
    // Resolves with the full user object if role matches; redirects otherwise.
    requireRole: function(requiredRole) {
        return new Promise((resolve) => {
            const unsub = auth.onAuthStateChanged(async (firebaseUser) => {
                unsub(); // one-shot — detach immediately

                // Case 5: not authenticated
                if (!firebaseUser) {
                    alert('Session expired. Please login to continue.');
                    Auth._redirectToLogin();
                    return;
                }

                // Case 4: DB read failure
                let userData = null;
                try {
                    userData = await DB.getUser(firebaseUser.uid);
                } catch (dbErr) {
                    console.error('Auth.requireRole: DB read error', dbErr);
                    alert('Unable to verify your account. Please login again.');
                    await auth.signOut();
                    sessionStorage.clear();
                    Auth._redirectToLogin();
                    return;
                }

                // Case 1: Auth OK but user node missing in DB
                if (!userData) {
                    alert('Account profile not found. Please register or contact support.');
                    await auth.signOut();
                    sessionStorage.clear();
                    Auth._redirectToLogin();
                    return;
                }

                // Case 2: Role field missing from DB record
                if (!userData.role) {
                    alert('No role assigned to this account. Contact the administrator.');
                    await auth.signOut();
                    sessionStorage.clear();
                    Auth._redirectToLogin();
                    return;
                }

                // Suspended account check
                if (userData.active === false || userData.status === 'Suspended') {
                    alert('Your account has been suspended. Contact the administrator.');
                    await auth.signOut();
                    sessionStorage.clear();
                    Auth._redirectToLogin();
                    return;
                }

                // Case 3: Role present but wrong for this page — redirect to their own dashboard
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
                        // Case 3 extended: role value is completely unknown/invalid
                        await auth.signOut();
                        sessionStorage.clear();
                        Auth._redirectToLogin();
                    }
                    return;
                }

                // All checks passed — persist session and resolve
                sessionStorage.setItem('uid', firebaseUser.uid);
                sessionStorage.setItem('userRole', userData.role);
                sessionStorage.setItem('userName', userData.name);
                resolve({ uid: firebaseUser.uid, ...userData });
            });
        });
    },

    // --- UPDATE PASSWORD ------------------------------------------
    updatePassword: function(newPassword) {
        const user = auth.currentUser;
        if (user) return user.updatePassword(newPassword);
        return Promise.reject('No user currently logged in.');
    },

    // --- CHECK 18+ AGE -------------------------------------------
    checkAge18: function(dob) {
        if (!dob) return false;
        const dobDate = new Date(dob);
        const today = new Date();
        let age = today.getFullYear() - dobDate.getFullYear();
        const m = today.getMonth() - dobDate.getMonth();
        if (m < 0 || (m === 0 && today.getDate() < dobDate.getDate())) age--;
        return age >= 18;
    },

    // --- MASK AADHAAR --------------------------------------------
    maskAadhaar: function(aadhaarNumber) {
        if (!aadhaarNumber || aadhaarNumber.length < 4) return 'XXXX XXXX XXXX';
        return 'XXXX XXXX ' + aadhaarNumber.slice(-4);
    },

    // --- MASK LICENSE --------------------------------------------
    maskLicense: function(licenseNumber) {
        if (!licenseNumber || licenseNumber.length < 4) return '****';
        return '****' + licenseNumber.slice(-4);
    }
};

// --- GLOBAL LOGOUT BINDER ------------------------------------
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
