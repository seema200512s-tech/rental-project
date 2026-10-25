-- =============================================================
-- RentRide — Complete MySQL Schema (authoritative)
-- Generated from backend/app.py SQL queries.
-- Run this ONCE on a FRESH MySQL server to create the database.
-- For an existing DB, run alter_db.sql instead.
-- =============================================================

CREATE DATABASE IF NOT EXISTS rentride
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE rentride;

-- =============================================================
-- 1. USERS
-- Stores all roles: 'user', 'owner', 'admin'
-- Referenced by: vehicles, bookings, payments, favorites,
--                maintenance (via owner_id / user_id)
-- =============================================================
CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4 (Firebase UID or generated)
    name          VARCHAR(255)  NOT NULL,
    email         VARCHAR(255)  NOT NULL UNIQUE,
    password_hash VARCHAR(255)  DEFAULT NULL,
    phone         VARCHAR(20)   DEFAULT NULL,
    dob           DATE          DEFAULT NULL,
    address       TEXT          DEFAULT NULL,
    role          VARCHAR(50)   NOT NULL DEFAULT 'user', -- 'user' | 'owner' | 'admin'
    active        BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- =============================================================
-- 2. VEHICLES
-- One owner (users.role = 'owner') → many vehicles
-- =============================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id               VARCHAR(36)   PRIMARY KEY,        -- uuid4
    owner_id         VARCHAR(36)   NOT NULL,
    brand            VARCHAR(100)  DEFAULT NULL,
    model            VARCHAR(100)  DEFAULT NULL,
    type             VARCHAR(50)   DEFAULT NULL,       -- 'SUV', 'Sedan', 'Car', 'Bike', etc.
    year             INT           DEFAULT NULL,
    fuel_type        VARCHAR(50)   DEFAULT NULL,
    transmission     VARCHAR(50)   DEFAULT NULL,       -- 'Automatic' | 'Manual'
    seats            INT           DEFAULT NULL,
    reg_no           VARCHAR(50)   DEFAULT NULL,
    price            DECIMAL(10,2) DEFAULT NULL,       -- daily rental price
    location         VARCHAR(255)  DEFAULT NULL,
    description      TEXT          DEFAULT NULL,
    status           VARCHAR(50)   NOT NULL DEFAULT 'Pending Approval',
        -- Possible: 'Available','Maintenance','Inactive','Rejected','Pending Approval'
    image_url        TEXT          DEFAULT NULL,
    document_url     TEXT          DEFAULT NULL,       -- RC, insurance, etc.
    rejection_reason TEXT          DEFAULT NULL,       -- set by admin on rejection
    created_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 3. BOOKINGS
-- Links a user to a vehicle for a date range.
-- =============================================================
CREATE TABLE IF NOT EXISTS bookings (
    id              VARCHAR(36)   PRIMARY KEY,         -- uuid4
    vehicle_id      VARCHAR(36)   NOT NULL,
    user_id         VARCHAR(36)   NOT NULL,
    owner_id        VARCHAR(36)   NOT NULL,
    start_date      DATE          NOT NULL,
    end_date        DATE          NOT NULL,
    status          VARCHAR(50)   NOT NULL DEFAULT 'Pending',
        -- Possible: 'Pending','Accepted','Confirmed','Active','Completed','Cancelled','Rejected'
    total_amount    DECIMAL(10,2) DEFAULT NULL,
    price_per_day   DECIMAL(10,2) DEFAULT NULL,
    days            INT           DEFAULT NULL,
    payment_status  VARCHAR(50)   NOT NULL DEFAULT 'Pending',
        -- Possible: 'Pending','Pending Verification','Paid','Rejected'
    license_number  VARCHAR(100)  DEFAULT NULL,
    license_expiry  DATE          DEFAULT NULL,
    aadhaar_last4   VARCHAR(20)   DEFAULT NULL,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    FOREIGN KEY (owner_id)   REFERENCES users(id)    ON DELETE CASCADE
) ENGINE=InnoDB;

-- Index for availability check (WHERE vehicle_id = ? AND status IN (...))
CREATE INDEX IF NOT EXISTS idx_bookings_vehicle_status
    ON bookings (vehicle_id, status, start_date, end_date);

-- =============================================================
-- 4. PAYMENTS
-- =============================================================
CREATE TABLE IF NOT EXISTS payments (
    id            VARCHAR(36)   PRIMARY KEY,           -- uuid4
    booking_id    VARCHAR(36)   NOT NULL,
    user_id       VARCHAR(36)   NOT NULL,
    owner_id      VARCHAR(36)   NOT NULL,
    vehicle_id    VARCHAR(36)   DEFAULT NULL,
    amount        DECIMAL(10,2) NOT NULL,
    status        VARCHAR(50)   NOT NULL DEFAULT 'Pending Verification',
        -- Possible: 'Pending Verification','Paid','Rejected'
    method        VARCHAR(50)   DEFAULT 'UPI',
    reference_no  VARCHAR(100)  DEFAULT NULL,
    payment_proof TEXT          DEFAULT NULL,
    admin_note    TEXT          DEFAULT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    FOREIGN KEY (owner_id)   REFERENCES users(id)    ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 5. FAVORITES
-- Many-to-many: users <-> vehicles
-- =============================================================
CREATE TABLE IF NOT EXISTS favorites (
    user_id       VARCHAR(36)   NOT NULL,
    vehicle_id    VARCHAR(36)   NOT NULL,

    PRIMARY KEY (user_id, vehicle_id),
    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 6. REVIEWS
-- =============================================================
CREATE TABLE IF NOT EXISTS reviews (
    id          VARCHAR(36)   PRIMARY KEY,             -- uuid4
    vehicle_id  VARCHAR(36)   NOT NULL,
    booking_id  VARCHAR(36)   NOT NULL,
    user_id     VARCHAR(36)   DEFAULT NULL,
    rating      INT           NOT NULL,                -- 1-5
    review_text TEXT          DEFAULT NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 7. MAINTENANCE
-- =============================================================
CREATE TABLE IF NOT EXISTS maintenance (
    id          VARCHAR(36)   PRIMARY KEY,             -- uuid4
    vehicle_id  VARCHAR(36)   NOT NULL,
    owner_id    VARCHAR(36)   NOT NULL,
    description TEXT          DEFAULT NULL,
    cost        DECIMAL(10,2) DEFAULT NULL,
    status      VARCHAR(50)   NOT NULL DEFAULT 'Pending',
    date        DATE          DEFAULT NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id)   REFERENCES users(id)    ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 8. NOTIFICATIONS
-- =============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id              VARCHAR(36)   PRIMARY KEY,         -- uuid4
    recipient_id    VARCHAR(36)   DEFAULT NULL,
    recipient_role  VARCHAR(50)   DEFAULT NULL,        -- 'admin' | 'owner' | 'user'
    title           VARCHAR(255)  DEFAULT NULL,
    message         TEXT          DEFAULT NULL,
    type            VARCHAR(50)   DEFAULT NULL,        -- 'vehicle_approval','booking_request', etc.
    status          VARCHAR(50)   NOT NULL DEFAULT 'unread',
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
