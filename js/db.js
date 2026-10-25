// js/db.js — Central Data Service connecting to RentRide Flask REST API & Firebase
// ─────────────────────────────────────────────────────────────

const DB = {
    // Helper for authenticated API calls
    _api: async function(path, options = {}) {
        const baseUrl = window.RENTRIDE_API_URL || 'http://127.0.0.1:5000';
        const token = sessionStorage.getItem('token');
        const headers = {
            'Accept': 'application/json',
            ...(options.headers || {})
        };
        if (token && !headers['Authorization']) {
            headers['Authorization'] = 'Bearer ' + token;
        }
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.body);
        }
        let res;
        try {
            res = await fetch(baseUrl + path, { ...options, headers });
        } catch (netErr) {
            console.error(`Network error requesting ${path}:`, netErr);
            throw new Error(`Cannot connect to backend server at ${baseUrl}. Please ensure the Flask backend is running on http://127.0.0.1:5000.`);
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Request failed (${res.status})`);
        }
        return res.json();
    },

    // ─── USERS ────────────────────────────────────────
    getUser: async function(uid) {
        if (!uid) return null;
        try {
            return await this._api(`/api/users/${uid}`);
        } catch (e) {
            console.warn('DB.getUser error:', e.message);
            return null;
        }
    },

    setUser: async function(uid, data) {
        return this.updateUser(uid, data);
    },

    updateUser: async function(uid, data) {
        try {
            return await this._api(`/api/users/${uid}`, {
                method: 'PUT',
                body: data
            });
        } catch (e) {
            console.error('DB.updateUser error:', e);
            throw e;
        }
    },

    getAllUsers: async function() {
        try {
            return await this._api('/api/users');
        } catch (e) {
            console.warn('DB.getAllUsers notice:', e.message);
            return [];
        }
    },

    getUsersByRole: async function(role) {
        try {
            return await this._api(`/api/users?role=${encodeURIComponent(role)}`);
        } catch (e) {
            console.warn('DB.getUsersByRole notice:', e.message);
            return [];
        }
    },

    // ─── VEHICLES ─────────────────────────────────────
    addVehicle: async function(vehicleData) {
        const res = await this._api('/api/vehicles', {
            method: 'POST',
            body: vehicleData
        });
        return res.id;
    },

    getVehicle: async function(vehicleId) {
        if (!vehicleId) return null;
        try {
            return await this._api(`/api/vehicles/${vehicleId}`);
        } catch (e) {
            console.warn('DB.getVehicle error:', e.message);
            return null;
        }
    },

    updateVehicle: async function(vehicleId, data) {
        return await this._api(`/api/vehicles/${vehicleId}`, {
            method: 'PUT',
            body: data
        });
    },

    deleteVehicle: async function(vehicleId) {
        return await this._api(`/api/vehicles/${vehicleId}`, {
            method: 'DELETE'
        });
    },

    getAllVehicles: async function() {
        try {
            return await this._api('/api/vehicles');
        } catch (e) {
            console.warn('DB.getAllVehicles error:', e.message);
            return [];
        }
    },

    getVehiclesByOwner: async function(ownerId) {
        try {
            return await this._api(`/api/vehicles?ownerId=${encodeURIComponent(ownerId)}`);
        } catch (e) {
            console.warn('DB.getVehiclesByOwner error:', e.message);
            return [];
        }
    },

    getAvailableVehicles: async function() {
        try {
            return await this._api('/api/vehicles?status=Available');
        } catch (e) {
            console.warn('DB.getAvailableVehicles error:', e.message);
            return [];
        }
    },

    // ─── BOOKINGS ─────────────────────────────────────
    addBooking: async function(bookingData) {
        const res = await this._api('/api/bookings', {
            method: 'POST',
            body: bookingData
        });
        return res.id;
    },

    getBooking: async function(bookingId) {
        if (!bookingId) return null;
        try {
            return await this._api(`/api/bookings/${bookingId}`);
        } catch (e) {
            console.warn('DB.getBooking error:', e.message);
            return null;
        }
    },

    updateBooking: async function(bookingId, data) {
        return await this._api(`/api/bookings/${bookingId}`, {
            method: 'PUT',
            body: data
        });
    },

    getAllBookings: async function() {
        try {
            return await this._api('/api/bookings');
        } catch (e) {
            console.warn('DB.getAllBookings error:', e.message);
            return [];
        }
    },

    getBookingsByUser: async function(userId) {
        try {
            return await this._api(`/api/bookings?userId=${encodeURIComponent(userId)}`);
        } catch (e) {
            console.warn('DB.getBookingsByUser error:', e.message);
            return [];
        }
    },

    getBookingsByOwner: async function(ownerId) {
        try {
            return await this._api(`/api/bookings?ownerId=${encodeURIComponent(ownerId)}`);
        } catch (e) {
            console.warn('DB.getBookingsByOwner error:', e.message);
            return [];
        }
    },

    // ─── SERVER-SIDE DATE OVERLAP CHECK ──────────────
    checkAvailability: async function(vehicleId, startDateStr, endDateStr) {
        try {
            const res = await this._api('/api/bookings/check-availability', {
                method: 'POST',
                body: {
                    vehicleId: vehicleId,
                    startDate: startDateStr,
                    endDate: endDateStr
                }
            });
            return res.available === true;
        } catch (e) {
            console.error('Error in checkAvailability:', e);
            return false;
        }
    },

    // ─── PAYMENTS ─────────────────────────────────────
    createPaymentOrder: async function(bookingId) {
        return await this._api('/api/payments/create-order', {
            method: 'POST',
            body: { bookingId: bookingId }
        });
    },

    verifyPayment: async function(verifyData) {
        return await this._api('/api/payments/verify', {
            method: 'POST',
            body: verifyData
        });
    },

    addPayment: async function(paymentData) {
        const res = await this._api('/api/payments', {
            method: 'POST',
            body: paymentData
        });
        return res.id;
    },

    updatePayment: async function(paymentId, data) {
        return await this._api(`/api/payments/${paymentId}`, {
            method: 'PUT',
            body: data
        });
    },

    getAllPayments: async function() {
        try {
            return await this._api('/api/payments');
        } catch (e) {
            console.warn('DB.getAllPayments error:', e.message);
            return [];
        }
    },

    getPaymentsByUser: async function(userId) {
        try {
            return await this._api(`/api/payments?userId=${encodeURIComponent(userId)}`);
        } catch (e) {
            console.warn('DB.getPaymentsByUser error:', e.message);
            return [];
        }
    },

    getPaymentsByOwner: async function(ownerId) {
        try {
            return await this._api(`/api/payments?ownerId=${encodeURIComponent(ownerId)}`);
        } catch (e) {
            console.warn('DB.getPaymentsByOwner error:', e.message);
            return [];
        }
    },

    // ─── FAVORITES ────────────────────────────────────
    addFavorite: async function(userId, vehicleId) {
        try {
            await this._api('/api/favorites', {
                method: 'POST',
                body: { userId, vehicleId }
            });
            return { success: true };
        } catch (e) {
            return { success: false };
        }
    },

    removeFavorite: async function(userId, vehicleId) {
        try {
            await this._api('/api/favorites', {
                method: 'DELETE',
                body: { userId, vehicleId }
            });
            return { success: true };
        } catch (e) {
            return { success: false };
        }
    },

    getFavorites: async function(userId) {
        try {
            return await this._api(`/api/favorites?userId=${encodeURIComponent(userId)}`);
        } catch (e) {
            return [];
        }
    },

    isFavorite: async function(userId, vehicleId) {
        try {
            const favs = await this.getFavorites(userId);
            return favs.includes(vehicleId);
        } catch (e) {
            return false;
        }
    },

    // ─── REVIEWS ──────────────────────────────────────
    addReview: async function(vehicleId, bookingId, reviewData) {
        const res = await this._api('/api/reviews', {
            method: 'POST',
            body: {
                vehicleId: vehicleId,
                bookingId: bookingId,
                rating: reviewData.rating,
                text: reviewData.text || reviewData.reviewText
            }
        });
        return res.id;
    },

    getReviewsForVehicle: async function(vehicleId) {
        try {
            return await this._api(`/api/reviews?vehicleId=${encodeURIComponent(vehicleId)}`);
        } catch (e) {
            return [];
        }
    },

    getAverageRating: async function(vehicleId) {
        try {
            const reviews = await this.getReviewsForVehicle(vehicleId);
            if (!reviews || reviews.length === 0) return { avg: '0.0', count: 0 };
            const sum = reviews.reduce((acc, r) => acc + Number(r.rating || 0), 0);
            return { avg: (sum / reviews.length).toFixed(1), count: reviews.length };
        } catch (e) {
            return { avg: '0.0', count: 0 };
        }
    },

    hasReviewedBooking: async function(vehicleId, bookingId) {
        try {
            const reviews = await this.getReviewsForVehicle(vehicleId);
            return reviews.some(r => String(r.bookingId) === String(bookingId));
        } catch (e) {
            return false;
        }
    },

    // ─── MAINTENANCE ──────────────────────────────────
    addMaintenance: async function(data) {
        const res = await this._api('/api/maintenance', {
            method: 'POST',
            body: data
        });
        return res.id;
    },

    updateMaintenance: async function(id, data) {
        return await this._api(`/api/maintenance/${id}`, {
            method: 'PUT',
            body: data
        });
    },

    getAllMaintenance: async function() {
        try {
            return await this._api('/api/maintenance');
        } catch (e) {
            return [];
        }
    },

    getMaintenanceByOwner: async function(ownerId) {
        try {
            return await this._api(`/api/maintenance?ownerId=${encodeURIComponent(ownerId)}`);
        } catch (e) {
            return [];
        }
    },

    // ─── IMAGE UPLOAD ─────────────────────────────────
    uploadImage: async function(file, pathStr) {
        // Try Flask backend multipart upload first
        if (file instanceof File || file instanceof Blob) {
            try {
                const formData = new FormData();
                formData.append('image', file);
                const baseUrl = window.RENTRIDE_API_URL || 'http://127.0.0.1:5000';
                const res = await fetch(baseUrl + '/api/vehicles/upload-image', {
                    method: 'POST',
                    body: formData
                });
                if (res.ok) {
                    const data = await res.json();
                    return baseUrl + data.url;
                }
            } catch (err) {
                console.warn('API upload failed, trying storage fallback:', err);
            }
        }

        // Firebase Storage fallback
        if (typeof storage !== 'undefined' && storage && file instanceof File) {
            try {
                const storageRef = storage.ref(`uploads/${Date.now()}_${file.name}`);
                const snapshot = await storageRef.put(file);
                return await snapshot.ref.getDownloadURL();
            } catch (err) {
                console.warn('Firebase Storage upload failed:', err);
            }
        }
        
        // Base64 Fallback
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = (err) => reject(err);
            if (file instanceof File || file instanceof Blob) {
                reader.readAsDataURL(file);
            } else {
                resolve(file);
            }
        });
    },

    // ─── NOTIFICATIONS ────────────────────────────────
    createNotification: async function(notificationData) {
        try {
            const res = await this._api('/api/notifications', {
                method: 'POST',
                body: notificationData
            });
            return res.id;
        } catch (e) {
            return null;
        }
    },

    markNotificationRead: async function(notificationId) {
        try {
            await this._api(`/api/notifications/${notificationId}`, {
                method: 'PUT',
                body: { status: 'read' }
            });
            return { success: true };
        } catch (e) {
            return { success: false };
        }
    },

    onAdminNotifications: function(callback) {
        // Fetch via API
        this._api('/api/notifications?recipientRole=admin').then(callback).catch(() => callback([]));
        
        // Also listen to Firebase RTDB if configured
        if (typeof database !== 'undefined' && database) {
            try {
                database.ref('notifications').on('value', snap => {
                    const val = snap.val() || {};
                    const list = Object.values(val).filter(n => n.recipientRole === 'admin');
                    if (list.length > 0) callback(list);
                });
            } catch (e) {}
        }
    },

    onOwnerNotifications: function(ownerId, callback) {
        // Fetch via API
        this._api(`/api/notifications?recipientId=${encodeURIComponent(ownerId)}`).then(callback).catch(() => callback([]));
        
        // Also listen to Firebase RTDB if configured
        if (typeof database !== 'undefined' && database) {
            try {
                database.ref('notifications').on('value', snap => {
                    const val = snap.val() || {};
                    const list = Object.values(val).filter(n => String(n.recipientId) === String(ownerId));
                    if (list.length > 0) callback(list);
                });
            } catch (e) {}
        }
    },

    offNotifications: function() {
        if (typeof database !== 'undefined' && database) {
            try {
                database.ref('notifications').off();
            } catch (e) {}
        }
    },

    // ─── SEED DATA ────────────────────────────────────
    seedIfEmpty: async function() {
        // Database is maintained securely via MySQL and backend/init_db.py.
        // No client-side public seeding needed, avoiding permission_denied errors.
        return Promise.resolve();
    }
};
