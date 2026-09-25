// js/db.js — Fetch Helpers for Flask REST API

const DB_API_BASE_URL = 'http://127.0.0.1:5000/api';

const fetchAPI = async (url, options = {}) => {
    const token = sessionStorage.getItem('token');
    if (token) {
        options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };
    }
    const response = await fetch(`${DB_API_BASE_URL}${url}`, options);
    
    // We try to parse the response as JSON regardless of status
    let data;
    try {
        data = await response.json();
    } catch (e) {
        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }
        return null; // Empty response body
    }

    if (!response.ok) {
        const errorMsg = data.error || data.message || response.statusText;
        throw new Error(errorMsg);
    }
    return data;
};

const DB = {

    // ─── USERS ────────────────────────────────────────
    getUser: function(uid) {
        return fetchAPI(`/users/${uid}`);
    },

    setUser: function(uid, data) {
        // Handled by auth.register now, but implemented for completeness
        return fetchAPI(`/users/${uid}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },

    updateUser: function(uid, data) {
        return fetchAPI(`/users/${uid}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },

    getAllUsers: function() {
        return fetchAPI('/users');
    },

    getUsersByRole: function(role) {
        return fetchAPI(`/users?role=${role}`);
    },

    // ─── VEHICLES ─────────────────────────────────────
    addVehicle: function(vehicleData) {
        return fetchAPI('/vehicles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(vehicleData)
        }).then(res => res.id);
    },

    getVehicle: function(vehicleId) {
        return fetchAPI(`/vehicles/${vehicleId}`).catch(() => null);
    },

    updateVehicle: function(vehicleId, data) {
        return fetchAPI(`/vehicles/${vehicleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },

    deleteVehicle: function(vehicleId) {
        return fetchAPI(`/vehicles/${vehicleId}`, { method: 'DELETE' });
    },

    getAllVehicles: function() {
        return fetchAPI('/vehicles');
    },

    getVehiclesByOwner: function(ownerId) {
        return fetchAPI(`/vehicles?ownerId=${ownerId}`);
    },

    getAvailableVehicles: function() {
        return fetchAPI('/vehicles?status=Available');
    },

    // ─── BOOKINGS ─────────────────────────────────────
    addBooking: function(bookingData) {
        return fetchAPI('/bookings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bookingData)
        }).then(res => res.id);
    },

    getBooking: function(bookingId) {
        return fetchAPI(`/bookings/${bookingId}`).catch(() => null);
    },

    updateBooking: function(bookingId, data) {
        return fetchAPI(`/bookings/${bookingId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },

    getAllBookings: function() {
        return fetchAPI('/bookings');
    },

    getBookingsByUser: function(userId) {
        return fetchAPI(`/bookings?userId=${userId}`);
    },

    getBookingsByOwner: function(ownerId) {
        return fetchAPI(`/bookings?ownerId=${ownerId}`);
    },

    // ─── CRITICAL: DATE OVERLAP CHECK ─────────────────
    checkAvailability: async function(vehicleId, startDateStr, endDateStr) {
        try {
            const res = await fetchAPI('/bookings/check-availability', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vehicleId, startDate: startDateStr, endDate: endDateStr })
            });
            return res.available;
        } catch (e) {
            console.error(e);
            return false;
        }
    },

    // ─── PAYMENTS ─────────────────────────────────────
    addPayment: function(paymentData) {
        return fetchAPI('/payments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(paymentData)
        }).then(res => res.id);
    },

    updatePayment: function(paymentId, data) {
        return fetchAPI(`/payments/${paymentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },

    getAllPayments: function() {
        return fetchAPI('/payments');
    },

    getPaymentsByUser: function(userId) {
        return fetchAPI(`/payments?userId=${userId}`);
    },

    getPaymentsByOwner: function(ownerId) {
        return fetchAPI(`/payments?ownerId=${ownerId}`);
    },

    // ─── FAVORITES ────────────────────────────────────
    addFavorite: function(userId, vehicleId) {
        return fetchAPI('/favorites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ userId, vehicleId })
        });
    },

    removeFavorite: function(userId, vehicleId) {
        return fetchAPI(`/favorites?userId=${userId}&vehicleId=${vehicleId}`, { method: 'DELETE' });
    },

    getFavorites: function(userId) {
        return fetchAPI(`/favorites?userId=${userId}`);
    },

    isFavorite: async function(userId, vehicleId) {
        const favs = await this.getFavorites(userId);
        return favs.includes(vehicleId);
    },

    // ─── REVIEWS ──────────────────────────────────────
    addReview: function(vehicleId, bookingId, reviewData) {
        return fetchAPI('/reviews', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vehicleId, bookingId, ...reviewData })
        });
    },

    getReviewsForVehicle: function(vehicleId) {
        return fetchAPI(`/reviews?vehicleId=${vehicleId}`);
    },

    getAverageRating: async function(vehicleId) {
        try {
            const reviews = await this.getReviewsForVehicle(vehicleId);
            if (!reviews || reviews.length === 0) return { avg: 0, count: 0 };
            const sum = reviews.reduce((acc, r) => acc + r.rating, 0);
            return { avg: (sum / reviews.length).toFixed(1), count: reviews.length };
        } catch(e) {
            return { avg: 0, count: 0 };
        }
    },

    hasReviewedBooking: async function(vehicleId, bookingId) {
        try {
            const reviews = await this.getReviewsForVehicle(vehicleId);
            return reviews.some(r => r.bookingId === bookingId);
        } catch(e) {
            return false;
        }
    },

    // ─── MAINTENANCE ──────────────────────────────────
    addMaintenance: function(data) {
        return fetchAPI('/maintenance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(res => res.id);
    },

    updateMaintenance: function(id, data) {
        return fetchAPI(`/maintenance/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    },

    getAllMaintenance: function() {
        return fetchAPI('/maintenance');
    },

    getMaintenanceByOwner: function(ownerId) {
        return fetchAPI(`/maintenance?ownerId=${ownerId}`);
    },

    // ─── IMAGE UPLOAD ─────────────────────────────────
    uploadImage: async function(file, path) {
        const formData = new FormData();
        formData.append('image', file);
        const res = await fetchAPI('/vehicles/upload-image', {
            method: 'POST',
            body: formData
        });
        // We must prepend the backend URL to the path since the frontend runs separately
        return `http://127.0.0.1:5000${res.url}`;
    },

    // ─── NOTIFICATIONS ────────────────────────────────
    createNotification: function(notificationData) {
        return fetchAPI('/notifications', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(notificationData)
        }).then(res => res.id);
    },

    markNotificationRead: function(notificationId) {
        return fetchAPI(`/notifications/${notificationId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'read' })
        });
    },

    // We can't do real-time callbacks easily with simple fetch, 
    // so we will simulate it with simple fetch calls
    onAdminNotifications: function(callback) {
        fetchAPI('/notifications?recipientRole=admin').then(callback).catch(() => callback([]));
    },

    onOwnerNotifications: function(ownerId, callback) {
        fetchAPI(`/notifications?recipientId=${ownerId}`).then(callback).catch(() => callback([]));
    },
    
    offNotifications: function() {
        // no-op
    },

    seedIfEmpty: async function() {
        // Server should handle seeding
    }
};
