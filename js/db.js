// js/db.js — Firebase Realtime Database helpers
// Requires firebase-config.js to be loaded first.

const DB = {

    // ─── USERS ────────────────────────────────────────
    getUser: function(uid) {
        return database.ref('users/' + uid).once('value').then(snap => snap.val());
    },

    setUser: function(uid, data) {
        return database.ref('users/' + uid).set(data);
    },

    updateUser: function(uid, data) {
        return database.ref('users/' + uid).update(data);
    },

    getAllUsers: function() {
        return database.ref('users').once('value').then(snap => {
            const data = snap.val() || {};
            return Object.entries(data).map(([id, val]) => ({ id, ...val }));
        });
    },

    getUsersByRole: function(role) {
        return database.ref('users').orderByChild('role').equalTo(role)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    // ─── VEHICLES ─────────────────────────────────────
    addVehicle: function(vehicleData) {
        const newRef = database.ref('vehicles').push();
        vehicleData.id = newRef.key;
        return newRef.set(vehicleData).then(() => newRef.key);
    },

    getVehicle: function(vehicleId) {
        return database.ref('vehicles/' + vehicleId).once('value').then(snap => {
            const val = snap.val();
            return val ? { id: vehicleId, ...val } : null;
        });
    },

    updateVehicle: function(vehicleId, data) {
        return database.ref('vehicles/' + vehicleId).update(data);
    },

    deleteVehicle: function(vehicleId) {
        return database.ref('vehicles/' + vehicleId).remove();
    },

    getAllVehicles: function() {
        return database.ref('vehicles').once('value').then(snap => {
            const data = snap.val() || {};
            return Object.entries(data).map(([id, val]) => ({ id, ...val }));
        });
    },

    getVehiclesByOwner: function(ownerId) {
        return database.ref('vehicles').orderByChild('ownerId').equalTo(ownerId)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    getAvailableVehicles: async function() {
        const snap = await database.ref('vehicles').once('value');
        const data = snap.val() || {};
        const allVehicles = Object.entries(data).map(([id, val]) => ({ id, ...val }));
        return allVehicles.filter(v => v.status === 'Available');
    },

    // ─── BOOKINGS ─────────────────────────────────────
    addBooking: function(bookingData) {
        const newRef = database.ref('bookings').push();
        bookingData.id = newRef.key;
        return newRef.set(bookingData).then(() => newRef.key);
    },

    getBooking: function(bookingId) {
        return database.ref('bookings/' + bookingId).once('value').then(snap => {
            const val = snap.val();
            return val ? { id: bookingId, ...val } : null;
        });
    },

    updateBooking: function(bookingId, data) {
        return database.ref('bookings/' + bookingId).update(data);
    },

    getAllBookings: function() {
        return database.ref('bookings').once('value').then(snap => {
            const data = snap.val() || {};
            return Object.entries(data).map(([id, val]) => ({ id, ...val }));
        });
    },

    getBookingsByUser: function(userId) {
        return database.ref('bookings').orderByChild('userId').equalTo(userId)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    getBookingsByOwner: function(ownerId) {
        return database.ref('bookings').orderByChild('ownerId').equalTo(ownerId)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    // ─── CRITICAL: DATE OVERLAP CHECK ─────────────────
    checkAvailability: async function(vehicleId, startDateStr, endDateStr) {
        const vehicle = await this.getVehicle(vehicleId);
        if (!vehicle || vehicle.status === 'Maintenance' || vehicle.status === 'Inactive' || vehicle.status === 'Rejected' || vehicle.status === 'Pending Approval') {
            return false;
        }

        const requestedStart = new Date(startDateStr);
        const requestedEnd = new Date(endDateStr);
        requestedStart.setHours(0, 0, 0, 0);
        requestedEnd.setHours(0, 0, 0, 0);

        if (requestedEnd < requestedStart) return false;

        const snap = await database.ref('bookings').orderByChild('vehicleId').equalTo(vehicleId).once('value');
        const bookings = snap.val() || {};

        for (const key in bookings) {
            const b = bookings[key];
            // Only active statuses block
            if (!['Pending', 'Accepted', 'Confirmed', 'Active'].includes(b.status)) continue;

            const bStart = new Date(b.startDate);
            const bEnd = new Date(b.endDate);
            bStart.setHours(0, 0, 0, 0);
            bEnd.setHours(0, 0, 0, 0);

            // Overlap: startA <= endB AND endA >= startB
            if (requestedStart <= bEnd && requestedEnd >= bStart) {
                return false;
            }
        }

        return true;
    },

    // ─── PAYMENTS ─────────────────────────────────────
    addPayment: function(paymentData) {
        const newRef = database.ref('payments').push();
        paymentData.id = newRef.key;
        return newRef.set(paymentData).then(() => newRef.key);
    },

    getAllPayments: function() {
        return database.ref('payments').once('value').then(snap => {
            const data = snap.val() || {};
            return Object.entries(data).map(([id, val]) => ({ id, ...val }));
        });
    },

    getPaymentsByUser: function(userId) {
        return database.ref('payments').orderByChild('userId').equalTo(userId)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    getPaymentsByOwner: function(ownerId) {
        return database.ref('payments').orderByChild('ownerId').equalTo(ownerId)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    // ─── FAVORITES ────────────────────────────────────
    addFavorite: function(userId, vehicleId) {
        return database.ref('favorites/' + userId + '/' + vehicleId).set(true);
    },

    removeFavorite: function(userId, vehicleId) {
        return database.ref('favorites/' + userId + '/' + vehicleId).remove();
    },

    getFavorites: function(userId) {
        return database.ref('favorites/' + userId).once('value').then(snap => {
            const data = snap.val() || {};
            return Object.keys(data);
        });
    },

    isFavorite: function(userId, vehicleId) {
        return database.ref('favorites/' + userId + '/' + vehicleId).once('value').then(snap => snap.exists());
    },

    // ─── REVIEWS ──────────────────────────────────────
    addReview: function(vehicleId, bookingId, reviewData) {
        return database.ref('reviews/' + vehicleId + '/' + bookingId).set(reviewData);
    },

    getReviewsForVehicle: function(vehicleId) {
        return database.ref('reviews/' + vehicleId).once('value').then(snap => {
            const data = snap.val() || {};
            return Object.entries(data).map(([bookingId, val]) => ({ bookingId, ...val }));
        });
    },

    getAverageRating: async function(vehicleId) {
        const reviews = await this.getReviewsForVehicle(vehicleId);
        if (reviews.length === 0) return { avg: 0, count: 0 };
        const sum = reviews.reduce((acc, r) => acc + r.rating, 0);
        return { avg: (sum / reviews.length).toFixed(1), count: reviews.length };
    },

    hasReviewedBooking: function(vehicleId, bookingId) {
        return database.ref('reviews/' + vehicleId + '/' + bookingId).once('value').then(snap => snap.exists());
    },

    // ─── MAINTENANCE ──────────────────────────────────
    addMaintenance: function(data) {
        const newRef = database.ref('maintenance').push();
        data.id = newRef.key;
        return newRef.set(data).then(() => newRef.key);
    },

    updateMaintenance: function(id, data) {
        return database.ref('maintenance/' + id).update(data);
    },

    getAllMaintenance: function() {
        return database.ref('maintenance').once('value').then(snap => {
            const data = snap.val() || {};
            return Object.entries(data).map(([id, val]) => ({ id, ...val }));
        });
    },

    getMaintenanceByOwner: function(ownerId) {
        return database.ref('maintenance').orderByChild('ownerId').equalTo(ownerId)
            .once('value').then(snap => {
                const data = snap.val() || {};
                return Object.entries(data).map(([id, val]) => ({ id, ...val }));
            });
    },

    // ─── IMAGE UPLOAD ─────────────────────────────────
    uploadImage: function(file, path) {
        const storageRef = storage.ref(path);
        return storageRef.put(file).then(snapshot => snapshot.ref.getDownloadURL());
    },

    // ─── NOTIFICATIONS ────────────────────────────────
    createNotification: function(notificationData) {
        const newRef = database.ref('notifications').push();
        notificationData.id = newRef.key;
        notificationData.status = 'unread';
        notificationData.createdAt = new Date().toISOString();
        return newRef.set(notificationData).then(() => newRef.key);
    },

    markNotificationRead: function(notificationId) {
        return database.ref('notifications/' + notificationId).update({ status: 'read' });
    },

    onAdminNotifications: function(callback) {
        return database.ref('notifications')
            .orderByChild('recipientRole')
            .equalTo('admin')
            .on('value', snap => {
                const data = snap.val() || {};
                const list = Object.entries(data).map(([id, val]) => ({ id, ...val }));
                callback(list);
            });
    },

    onOwnerNotifications: function(ownerId, callback) {
        return database.ref('notifications')
            .orderByChild('recipientId')
            .equalTo(ownerId)
            .on('value', snap => {
                const data = snap.val() || {};
                const list = Object.entries(data).map(([id, val]) => ({ id, ...val })).filter(n => n.recipientRole === 'owner');
                callback(list);
            });
    },
    
    offNotifications: function() {
        database.ref('notifications').off();
    },

    // ─── SEED DATA ────────────────────────────────────
    seedIfEmpty: async function() {
        const snap = await database.ref('seeded').once('value');
        if (snap.val()) return; // Already seeded

        // Seed admin user directly in DB (admin won't register via form)
        // The admin account will be created in Firebase Auth manually or via first-run
        console.log('Seeding initial data...');

        // Seed some sample vehicles (will be linked to demo owner later)
        const sampleVehicles = {
            'v1': {
                id: 'v1',
                ownerId: 'DEMO_OWNER',
                brand: 'Honda',
                model: 'City',
                type: 'Car',
                year: 2023,
                fuelType: 'Petrol',
                transmission: 'Automatic',
                seats: 5,
                regNo: 'MH-12-AB-1234',
                price: 1800,
                location: 'Mumbai',
                description: 'Premium sedan, well maintained, perfect for city drives.',
                status: 'Available',
                imageUrl: 'https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?auto=format&fit=crop&q=80&w=600',
                createdAt: new Date().toISOString()
            },
            'v2': {
                id: 'v2',
                ownerId: 'DEMO_OWNER',
                brand: 'Royal Enfield',
                model: 'Classic 350',
                type: 'Bike',
                year: 2024,
                fuelType: 'Petrol',
                transmission: 'Manual',
                seats: 2,
                regNo: 'MH-14-CD-5678',
                price: 800,
                location: 'Pune',
                description: 'Iconic cruiser bike, perfect for long weekend rides.',
                status: 'Available',
                imageUrl: 'https://images.unsplash.com/photo-1558981403-c5f9899a28bc?auto=format&fit=crop&q=80&w=600',
                createdAt: new Date().toISOString()
            },
            'v3': {
                id: 'v3',
                ownerId: 'DEMO_OWNER',
                brand: 'Mahindra',
                model: 'Thar',
                type: 'SUV',
                year: 2024,
                fuelType: 'Diesel',
                transmission: 'Manual',
                seats: 4,
                regNo: 'MH-01-EF-9012',
                price: 3000,
                location: 'Mumbai',
                description: 'Adventure-ready 4x4 SUV for off-road experiences.',
                status: 'Available',
                imageUrl: 'https://images.unsplash.com/photo-1502877338535-766e1452684a?auto=format&fit=crop&q=80&w=600',
                createdAt: new Date().toISOString()
            },
            'v4': {
                id: 'v4',
                ownerId: 'DEMO_OWNER',
                brand: 'Toyota',
                model: 'Innova Crysta',
                type: 'Car',
                year: 2023,
                fuelType: 'Diesel',
                transmission: 'Automatic',
                seats: 7,
                regNo: 'MH-04-GH-3456',
                price: 2500,
                location: 'Delhi',
                description: 'Spacious family MPV with comfortable ride.',
                status: 'Available',
                imageUrl: 'https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&q=80&w=600',
                createdAt: new Date().toISOString()
            }
        };

        await database.ref('vehicles').set(sampleVehicles);
        await database.ref('seeded').set(true);
        console.log('Seed data written successfully.');
    }
};
