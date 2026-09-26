// js/db.js — Firebase Realtime Database & Storage Integration

const DB = {

    // ─── USERS ────────────────────────────────────────
    getUser: async function(uid) {
        if (!uid || !database) return null;
        const snap = await database.ref('users/' + uid).once('value');
        return snap.val() || null;
    },

    setUser: async function(uid, data) {
        if (!database) return null;
        await database.ref('users/' + uid).set(data);
        return data;
    },

    updateUser: async function(uid, data) {
        if (!database) return null;
        await database.ref('users/' + uid).update(data);
        return { success: true };
    },

    getAllUsers: async function() {
        if (!database) return [];
        const snap = await database.ref('users').once('value');
        const val = snap.val() || {};
        return Object.values(val);
    },

    getUsersByRole: async function(role) {
        const users = await this.getAllUsers();
        return users.filter(u => u.role === role);
    },

    // ─── VEHICLES ─────────────────────────────────────
    addVehicle: async function(vehicleData) {
        if (!database) throw new Error('Database not initialized');
        const ref = database.ref('vehicles').push();
        const id = ref.key;
        const vehicleObj = {
            ...vehicleData,
            id: id,
            status: vehicleData.status || 'Pending Approval',
            createdAt: new Date().toISOString()
        };
        await ref.set(vehicleObj);
        return id;
    },

    getVehicle: async function(vehicleId) {
        if (!vehicleId || !database) return null;
        const snap = await database.ref('vehicles/' + vehicleId).once('value');
        return snap.val() || null;
    },

    updateVehicle: async function(vehicleId, data) {
        if (!database) return { success: false };
        await database.ref('vehicles/' + vehicleId).update(data);
        return { success: true };
    },

    deleteVehicle: async function(vehicleId) {
        if (!database) return { success: false };
        await database.ref('vehicles/' + vehicleId).remove();
        return { success: true };
    },

    getAllVehicles: async function() {
        if (!database) return [];
        const snap = await database.ref('vehicles').once('value');
        const val = snap.val() || {};
        return Object.values(val);
    },

    getVehiclesByOwner: async function(ownerId) {
        const vehicles = await this.getAllVehicles();
        return vehicles.filter(v => String(v.ownerId) === String(ownerId));
    },

    getAvailableVehicles: async function() {
        const vehicles = await this.getAllVehicles();
        return vehicles.filter(v => v.status === 'Available');
    },

    // ─── BOOKINGS ─────────────────────────────────────
    addBooking: async function(bookingData) {
        if (!database) throw new Error('Database not initialized');
        const ref = database.ref('bookings').push();
        const id = ref.key;
        const bookingObj = {
            ...bookingData,
            id: id,
            status: bookingData.status || 'Confirmed',
            createdAt: new Date().toISOString()
        };
        await ref.set(bookingObj);
        return id;
    },

    getBooking: async function(bookingId) {
        if (!bookingId || !database) return null;
        const snap = await database.ref('bookings/' + bookingId).once('value');
        return snap.val() || null;
    },

    updateBooking: async function(bookingId, data) {
        if (!database) return { success: false };
        await database.ref('bookings/' + bookingId).update(data);
        return { success: true };
    },

    getAllBookings: async function() {
        if (!database) return [];
        const snap = await database.ref('bookings').once('value');
        const val = snap.val() || {};
        return Object.values(val);
    },

    getBookingsByUser: async function(userId) {
        const bookings = await this.getAllBookings();
        return bookings.filter(b => String(b.userId) === String(userId));
    },

    getBookingsByOwner: async function(ownerId) {
        const bookings = await this.getAllBookings();
        return bookings.filter(b => String(b.ownerId) === String(ownerId));
    },

    // ─── CRITICAL: DATE OVERLAP CHECK ─────────────────
    checkAvailability: async function(vehicleId, startDateStr, endDateStr) {
        try {
            const start = new Date(startDateStr);
            const end = new Date(endDateStr);
            const allBookings = await this.getAllBookings();

            const overlapping = allBookings.some(b => {
                if (String(b.vehicleId) !== String(vehicleId)) return false;
                if (b.status === 'Cancelled' || b.status === 'Rejected') return false;
                
                const bStart = new Date(b.startDate);
                const bEnd = new Date(b.endDate);
                
                return (start <= bEnd && end >= bStart);
            });

            return !overlapping;
        } catch (e) {
            console.error('Error in checkAvailability:', e);
            return false;
        }
    },

    // ─── PAYMENTS ─────────────────────────────────────
    addPayment: async function(paymentData) {
        if (!database) throw new Error('Database not initialized');
        const ref = database.ref('payments').push();
        const id = ref.key;
        const paymentObj = {
            ...paymentData,
            id: id,
            status: paymentData.status || 'Completed',
            createdAt: new Date().toISOString()
        };
        await ref.set(paymentObj);
        return id;
    },

    updatePayment: async function(paymentId, data) {
        if (!database) return { success: false };
        await database.ref('payments/' + paymentId).update(data);
        return { success: true };
    },

    getAllPayments: async function() {
        if (!database) return [];
        const snap = await database.ref('payments').once('value');
        const val = snap.val() || {};
        return Object.values(val);
    },

    getPaymentsByUser: async function(userId) {
        const payments = await this.getAllPayments();
        return payments.filter(p => String(p.userId) === String(userId));
    },

    getPaymentsByOwner: async function(ownerId) {
        const payments = await this.getAllPayments();
        return payments.filter(p => String(p.ownerId) === String(ownerId));
    },

    // ─── FAVORITES ────────────────────────────────────
    addFavorite: async function(userId, vehicleId) {
        if (!database) return { success: false };
        await database.ref(`favorites/${userId}/${vehicleId}`).set(true);
        return { success: true };
    },

    removeFavorite: async function(userId, vehicleId) {
        if (!database) return { success: false };
        await database.ref(`favorites/${userId}/${vehicleId}`).remove();
        return { success: true };
    },

    getFavorites: async function(userId) {
        if (!database) return [];
        const snap = await database.ref(`favorites/${userId}`).once('value');
        const val = snap.val() || {};
        return Object.keys(val);
    },

    isFavorite: async function(userId, vehicleId) {
        if (!database) return false;
        const snap = await database.ref(`favorites/${userId}/${vehicleId}`).once('value');
        return snap.exists();
    },

    // ─── REVIEWS ──────────────────────────────────────
    addReview: async function(vehicleId, bookingId, reviewData) {
        if (!database) throw new Error('Database not initialized');
        const ref = database.ref('reviews').push();
        const id = ref.key;
        const reviewObj = {
            ...reviewData,
            vehicleId: vehicleId,
            bookingId: bookingId,
            id: id,
            createdAt: new Date().toISOString()
        };
        await ref.set(reviewObj);
        return id;
    },

    getReviewsForVehicle: async function(vehicleId) {
        if (!database) return [];
        const snap = await database.ref('reviews').once('value');
        const val = snap.val() || {};
        const reviews = Object.values(val);
        return reviews.filter(r => String(r.vehicleId) === String(vehicleId));
    },

    getAverageRating: async function(vehicleId) {
        try {
            const reviews = await this.getReviewsForVehicle(vehicleId);
            if (!reviews || reviews.length === 0) return { avg: 0, count: 0 };
            const sum = reviews.reduce((acc, r) => acc + Number(r.rating || 0), 0);
            return { avg: (sum / reviews.length).toFixed(1), count: reviews.length };
        } catch(e) {
            return { avg: 0, count: 0 };
        }
    },

    hasReviewedBooking: async function(vehicleId, bookingId) {
        try {
            const reviews = await this.getReviewsForVehicle(vehicleId);
            return reviews.some(r => String(r.bookingId) === String(bookingId));
        } catch(e) {
            return false;
        }
    },

    // ─── MAINTENANCE ──────────────────────────────────
    addMaintenance: async function(data) {
        if (!database) throw new Error('Database not initialized');
        const ref = database.ref('maintenance').push();
        const id = ref.key;
        const mainObj = {
            ...data,
            id: id,
            status: data.status || 'Pending',
            createdAt: new Date().toISOString()
        };
        await ref.set(mainObj);
        return id;
    },

    updateMaintenance: async function(id, data) {
        if (!database) return { success: false };
        await database.ref(`maintenance/${id}`).update(data);
        return { success: true };
    },

    getAllMaintenance: async function() {
        if (!database) return [];
        const snap = await database.ref('maintenance').once('value');
        const val = snap.val() || {};
        return Object.values(val);
    },

    getMaintenanceByOwner: async function(ownerId) {
        const list = await this.getAllMaintenance();
        return list.filter(m => String(m.ownerId) === String(ownerId));
    },

    // ─── IMAGE UPLOAD ─────────────────────────────────
    uploadImage: async function(file, pathStr) {
        if (storage && file instanceof File) {
            try {
                const storageRef = storage.ref(`uploads/${Date.now()}_${file.name}`);
                const snapshot = await storageRef.put(file);
                const downloadURL = await snapshot.ref.getDownloadURL();
                return downloadURL;
            } catch (err) {
                console.warn('Firebase Storage upload failed, converting to Base64 image:', err);
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
                resolve(file); // Already a URL or string
            }
        });
    },

    // ─── NOTIFICATIONS ────────────────────────────────
    createNotification: async function(notificationData) {
        if (!database) return null;
        const ref = database.ref('notifications').push();
        const id = ref.key;
        const notifObj = {
            ...notificationData,
            id: id,
            status: 'unread',
            createdAt: new Date().toISOString()
        };
        await ref.set(notifObj);
        return id;
    },

    markNotificationRead: async function(notificationId) {
        if (!database) return { success: false };
        await database.ref(`notifications/${notificationId}`).update({ status: 'read' });
        return { success: true };
    },

    onAdminNotifications: function(callback) {
        if (!database) return;
        return database.ref('notifications').on('value', snap => {
            const val = snap.val() || {};
            const list = Object.values(val).filter(n => n.recipientRole === 'admin');
            callback(list);
        });
    },

    onOwnerNotifications: function(ownerId, callback) {
        if (!database) return;
        return database.ref('notifications').on('value', snap => {
            const val = snap.val() || {};
            const list = Object.values(val).filter(n => String(n.recipientId) === String(ownerId));
            callback(list);
        });
    },

    offNotifications: function() {
        if (database) {
            database.ref('notifications').off();
        }
    },

    // ─── SEED DATA ────────────────────────────────────
    seedIfEmpty: async function() {
        if (!database) return;
        try {
            const snap = await database.ref('vehicles').once('value');
            if (snap.exists() && Object.keys(snap.val() || {}).length > 0) {
                return; // Already seeded
            }

            console.log('Seeding initial vehicle data into Firebase Realtime Database...');
            const sampleVehicles = [
                {
                    id: "v1",
                    brand: "Tesla",
                    model: "Model 3",
                    type: "Electric",
                    year: 2023,
                    fuel_type: "Electric",
                    transmission: "Automatic",
                    seats: 5,
                    reg_no: "KA-01-EQ-1234",
                    price: 4500,
                    location: "Bangalore",
                    description: "Sleek and eco-friendly electric sedan with Autopilot feature.",
                    status: "Available",
                    image_url: "https://images.unsplash.com/photo-1560958089-b8a1929cea89?w=800&auto=format&fit=crop&q=80",
                    ownerId: "owner1"
                },
                {
                    id: "v2",
                    brand: "BMW",
                    model: "X5",
                    type: "SUV",
                    year: 2022,
                    fuel_type: "Petrol",
                    transmission: "Automatic",
                    seats: 7,
                    reg_no: "KA-05-MH-9999",
                    price: 6500,
                    location: "Mumbai",
                    description: "Luxury SUV with panoramic sunroof and premium audio system.",
                    status: "Available",
                    image_url: "https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&auto=format&fit=crop&q=80",
                    ownerId: "owner1"
                },
                {
                    id: "v3",
                    brand: "Hyundai",
                    model: "Creta",
                    type: "SUV",
                    year: 2023,
                    fuel_type: "Diesel",
                    transmission: "Manual",
                    seats: 5,
                    reg_no: "DL-03-CC-4321",
                    price: 2500,
                    location: "Delhi",
                    description: "Reliable city SUV with great fuel economy and smooth ride.",
                    status: "Available",
                    image_url: "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800&auto=format&fit=crop&q=80",
                    ownerId: "owner2"
                }
            ];

            const seedObj = {};
            sampleVehicles.forEach(v => {
                seedObj[v.id] = v;
            });

            await database.ref('vehicles').update(seedObj);
            console.log('Firebase seeding complete.');
        } catch (e) {
            console.error('Failed to seed Firebase Realtime Database:', e);
        }
    }
};

