-- =============================================================
-- RentRide — Safe ALTER TABLE to add missing columns
-- Run this ONCE in MySQL Workbench (or mysql CLI) if your database
-- was created from the OLD rentride_schema.sql (before this fix).
-- All statements use IF NOT EXISTS / ALTER IGNORE so they are safe
-- to re-run on an already-updated database.
-- =============================================================

USE rentride;

-- ─── VEHICLES ───────────────────────────────────────────────
ALTER TABLE vehicles
    ADD COLUMN IF NOT EXISTS document_url    TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT        DEFAULT NULL;

-- ─── BOOKINGS ───────────────────────────────────────────────
ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS price_per_day  DECIMAL(10,2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS days           INT           DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50)   NOT NULL DEFAULT 'Pending',
    ADD COLUMN IF NOT EXISTS license_number VARCHAR(100)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS license_expiry DATE          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS aadhaar_last4  VARCHAR(20)   DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR(100) DEFAULT NULL;

-- ─── PAYMENTS ───────────────────────────────────────────────
ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS vehicle_id     VARCHAR(36)   DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS method         VARCHAR(50)   DEFAULT 'UPI',
    ADD COLUMN IF NOT EXISTS reference_no   VARCHAR(100)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS payment_proof  TEXT          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS admin_note     TEXT          DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR(100) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR(100) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS razorpay_signature TEXT DEFAULT NULL;

-- Update payments.status default to match app.py expectations
ALTER TABLE payments
    MODIFY COLUMN status VARCHAR(50) NOT NULL DEFAULT 'Pending Verification';

-- ─── REVIEWS ────────────────────────────────────────────────
ALTER TABLE reviews
    ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) DEFAULT NULL;

-- ─── NOTIFICATIONS ──────────────────────────────────────────
-- (notifications.type is used in app.py inserts)
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS type VARCHAR(50) DEFAULT NULL;

-- ─── DONE ───────────────────────────────────────────────────
SELECT 'alter_db.sql applied successfully.' AS result;
