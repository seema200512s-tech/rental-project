TablesTablesusersreviewspayments-- =============================================================
-- RentRide — Complete MySQL Schema
-- Generated from the existing backend/app.py SQL queries.
-- Run this ONCE on a fresh MySQL server to create the database.
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
--
-- Columns used in app.py:
--   INSERT: id, name, email, password_hash, phone, dob, address, role
--   SELECT: id, name, email, password_hash (login), phone, dob,
--           address, role, active, created_at
--   UPDATE: name, phone, address, active
-- =============================================================
CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4
    name          VARCHAR(255)  NOT NULL,
    email         VARCHAR(255)  NOT NULL UNIQUE,
    password_hash VARCHAR(255)  NOT NULL,
    phone         VARCHAR(20)   DEFAULT NULL,
    dob           DATE          DEFAULT NULL,
    address       TEXT          DEFAULT NULL,
    role          VARCHAR(50)   NOT NULL,             -- 'user' | 'owner' | 'admin'
    active        BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- =============================================================
-- 2. VEHICLES
-- One owner (users.role = 'owner') → many vehicles
--
-- Columns used in app.py:
--   INSERT: id, owner_id, brand, model, type, year, fuel_type,
--           transmission, seats, reg_no, price, location,
--           description, status, image_url
--   SELECT *  (all columns)
--   UPDATE: brand, model, type, year, fuel_type, transmission,
--           seats, reg_no, price, location, description, status,
--           image_url
--   DELETE: by id
-- =============================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4
    owner_id      VARCHAR(36)   NOT NULL,
    brand         VARCHAR(100)  DEFAULT NULL,
    model         VARCHAR(100)  DEFAULT NULL,
    type          VARCHAR(50)   DEFAULT NULL,         -- 'SUV', 'Sedan', etc.
    year          INT           DEFAULT NULL,
    fuel_type     VARCHAR(50)   DEFAULT NULL,
    transmission  VARCHAR(50)   DEFAULT NULL,         -- 'Automatic' | 'Manual'
    seats         INT           DEFAULT NULL,
    reg_no        VARCHAR(50)   DEFAULT NULL,
    price         DECIMAL(10,2) DEFAULT NULL,         -- daily rental price
    location      VARCHAR(255)  DEFAULT NULL,
    description   TEXT          DEFAULT NULL,
    status        VARCHAR(50)   NOT NULL DEFAULT 'Available',
        -- Possible: 'Available','Maintenance','Inactive',
        --           'Rejected','Pending Approval'
    image_url     TEXT          DEFAULT NULL,         -- path or full URL
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 3. BOOKINGS
-- Links a user to a vehicle for a date range.
-- The check-availability endpoint compares start_date / end_date
-- for overlap with status IN ('Pending','Accepted','Confirmed','Active').
--
-- Columns used in app.py:
--   INSERT: id, vehicle_id, user_id, owner_id, start_date,
--           end_date, status, total_amount
--   SELECT *  (all columns, filtered by user_id / owner_id)
--   UPDATE: status
-- =============================================================
CREATE TABLE IF NOT EXISTS bookings (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4
    vehicle_id    VARCHAR(36)   NOT NULL,
    user_id       VARCHAR(36)   NOT NULL,
    owner_id      VARCHAR(36)   NOT NULL,
    start_date    DATE          NOT NULL,
    end_date      DATE          NOT NULL,
    status        VARCHAR(50)   NOT NULL DEFAULT 'Pending',
        -- Possible: 'Pending','Accepted','Confirmed','Active',
        --           'Completed','Cancelled','Rejected'
    total_amount  DECIMAL(10,2) DEFAULT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    FOREIGN KEY (owner_id)   REFERENCES users(id)    ON DELETE CASCADE
) ENGINE=InnoDB;

-- Index to speed up the date-overlap availability check
-- (WHERE vehicle_id = ? AND status IN (...))
CREATE INDEX idx_bookings_vehicle_status
    ON bookings (vehicle_id, status, start_date, end_date);

-- =============================================================
-- 4. PAYMENTS
--
-- Columns used in app.py:
--   INSERT: id, booking_id, user_id, owner_id, amount, status
--   SELECT *  (all columns, filtered by user_id / owner_id)
-- =============================================================
CREATE TABLE IF NOT EXISTS payments (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4
    booking_id    VARCHAR(36)   NOT NULL,
    user_id       VARCHAR(36)   NOT NULL,
    owner_id      VARCHAR(36)   NOT NULL,
    amount        DECIMAL(10,2) NOT NULL,
    status        VARCHAR(50)   NOT NULL DEFAULT 'Completed',
        -- Possible: 'Completed','Paid','Pending','Refunded'
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (owner_id)   REFERENCES users(id)     ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 5. FAVORITES
-- Many-to-many: users <-> vehicles
-- Uses INSERT IGNORE, so the composite PK prevents duplicates.
--
-- Columns used in app.py:
--   INSERT IGNORE: user_id, vehicle_id
--   SELECT: vehicle_id WHERE user_id = ?
--   DELETE: WHERE user_id = ? AND vehicle_id = ?
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
--
-- Columns used in app.py:
--   INSERT: id, vehicle_id, booking_id, rating, review_text
--   SELECT *  WHERE vehicle_id = ?
-- =============================================================
CREATE TABLE IF NOT EXISTS reviews (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4
    vehicle_id    VARCHAR(36)   NOT NULL,
    booking_id    VARCHAR(36)   NOT NULL,
    rating        INT           NOT NULL,             -- 1-5
    review_text   TEXT          DEFAULT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 7. MAINTENANCE
--
-- Columns used in app.py:
--   INSERT: id, vehicle_id, owner_id, description, cost,
--           status, date
--   SELECT *  (all columns, filtered by owner_id)
--   UPDATE: description, cost, status, date
-- =============================================================
CREATE TABLE IF NOT EXISTS maintenance (
    id            VARCHAR(36)   PRIMARY KEY,          -- uuid4
    vehicle_id    VARCHAR(36)   NOT NULL,
    owner_id      VARCHAR(36)   NOT NULL,
    description   TEXT          DEFAULT NULL,
    cost          DECIMAL(10,2) DEFAULT NULL,
    status        VARCHAR(50)   NOT NULL DEFAULT 'Pending',
    date          DATE          DEFAULT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id)   REFERENCES users(id)    ON DELETE CASCADE
) ENGINE=InnoDB;

-- =============================================================
-- 8. NOTIFICATIONS
-- Used by the existing backend notification endpoints.
--
-- Columns used in app.py:
--   INSERT: id, recipient_id, recipient_role, title, message
--   SELECT *  (filtered by recipient_role or recipient_id)
--   UPDATE: status
-- =============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id              VARCHAR(36)   PRIMARY KEY,        -- uuid4
    recipient_id    VARCHAR(36)   DEFAULT NULL,
    recipient_role  VARCHAR(50)   DEFAULT NULL,       -- 'admin' | 'owner' | 'user'
    title           VARCHAR(255)  DEFAULT NULL,
    message         TEXT          DEFAULT NULL,
    status          VARCHAR(50)   NOT NULL DEFAULT 'unread',
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
