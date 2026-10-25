import os
import sys
import uuid
import mysql.connector
from werkzeug.security import generate_password_hash

# Ensure config can be imported from backend directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import Config

def init_database():
    print(f"Connecting to MySQL server at {Config.MYSQL_HOST}:{Config.MYSQL_PORT} as {Config.MYSQL_USER}...")
    
    # 1. Connect without database to ensure rentride DB exists
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        port=Config.MYSQL_PORT
    )
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS rentride DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cursor.close()
    conn.close()

    # 2. Connect to rentride DB
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        port=Config.MYSQL_PORT,
        database=Config.MYSQL_DB
    )
    cursor = conn.cursor()

    # Create tables
    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) DEFAULT NULL,
            phone VARCHAR(20) DEFAULT NULL,
            dob DATE DEFAULT NULL,
            address TEXT DEFAULT NULL,
            role VARCHAR(50) NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            id VARCHAR(255) PRIMARY KEY,
            owner_id VARCHAR(255) NOT NULL,
            brand VARCHAR(100) NOT NULL,
            model VARCHAR(100) NOT NULL,
            type VARCHAR(50) DEFAULT 'Sedan',
            year INT DEFAULT 2023,
            fuel_type VARCHAR(50) DEFAULT 'Petrol',
            transmission VARCHAR(50) DEFAULT 'Automatic',
            seats INT DEFAULT 5,
            reg_no VARCHAR(50) DEFAULT NULL,
            price DECIMAL(10, 2) NOT NULL,
            location VARCHAR(255) DEFAULT 'Bangalore',
            description TEXT DEFAULT NULL,
            status VARCHAR(50) DEFAULT 'Pending Approval',
            image_url TEXT DEFAULT NULL,
            document_url TEXT DEFAULT NULL,
            rejection_reason TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id VARCHAR(255) PRIMARY KEY,
            vehicle_id VARCHAR(255) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            owner_id VARCHAR(255) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status VARCHAR(50) DEFAULT 'Pending',
            total_amount DECIMAL(10, 2) NOT NULL,
            price_per_day DECIMAL(10, 2) DEFAULT 0,
            days INT DEFAULT 1,
            payment_status VARCHAR(50) DEFAULT 'Pending',
            license_number VARCHAR(100) DEFAULT NULL,
            license_expiry DATE DEFAULT NULL,
            aadhaar_last4 VARCHAR(100) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS payments (
            id VARCHAR(255) PRIMARY KEY,
            booking_id VARCHAR(255) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            owner_id VARCHAR(255) NOT NULL,
            vehicle_id VARCHAR(255) DEFAULT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'Pending Verification',
            method VARCHAR(50) DEFAULT 'UPI',
            reference_no VARCHAR(255) DEFAULT NULL,
            payment_proof TEXT DEFAULT NULL,
            admin_note TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS favorites (
            user_id VARCHAR(255) NOT NULL,
            vehicle_id VARCHAR(255) NOT NULL,
            PRIMARY KEY (user_id, vehicle_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id VARCHAR(255) PRIMARY KEY,
            vehicle_id VARCHAR(255) NOT NULL,
            booking_id VARCHAR(255) NOT NULL,
            user_id VARCHAR(255) DEFAULT NULL,
            rating INT NOT NULL,
            review_text TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS maintenance (
            id VARCHAR(255) PRIMARY KEY,
            vehicle_id VARCHAR(255) NOT NULL,
            owner_id VARCHAR(255) NOT NULL,
            description TEXT DEFAULT NULL,
            cost DECIMAL(10, 2) DEFAULT 0,
            status VARCHAR(50) DEFAULT 'Pending',
            date DATE DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """,
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id VARCHAR(255) PRIMARY KEY,
            recipient_id VARCHAR(255) DEFAULT NULL,
            recipient_role VARCHAR(50) DEFAULT NULL,
            title VARCHAR(255) DEFAULT NULL,
            message TEXT DEFAULT NULL,
            type VARCHAR(50) DEFAULT NULL,
            status VARCHAR(50) DEFAULT 'unread',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """
    ]

    for statement in tables:
        cursor.execute(statement)
    conn.commit()

    # Seed default accounts if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    admin_id = "user_admin_001"
    owner_id = "user_owner_001"
    renter_id = "user_renter_001"

    if count == 0:
        demo_users = [
            (admin_id, "System Admin", "admin@rentride.com", generate_password_hash("admin123", method="pbkdf2:sha256"), "9876543210", "1990-01-01", "Admin HQ, City", "admin", True),
            (owner_id, "Vehicle Owner", "owner@rentride.com", generate_password_hash("owner123", method="pbkdf2:sha256"), "9876543211", "1992-05-15", "Owner St, City", "owner", True),
            (renter_id, "Demo User", "user@rentride.com", generate_password_hash("user123", method="pbkdf2:sha256"), "9876543212", "1995-10-20", "User Ave, City", "user", True)
        ]
        cursor.executemany(
            "INSERT INTO users (id, name, email, password_hash, phone, dob, address, role, active) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            demo_users
        )
        conn.commit()
        print("Seeded default users (admin@rentride.com / admin123, owner@rentride.com / owner123, user@rentride.com / user123).")

    # Seed vehicles if empty
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    v_count = cursor.fetchone()[0]
    if v_count == 0:
        # Find the owner id
        cursor.execute("SELECT id FROM users WHERE role = 'owner' LIMIT 1")
        row = cursor.fetchone()
        actual_owner_id = row[0] if row else owner_id

        sample_vehicles = [
            (
                "v1", actual_owner_id, "Tesla", "Model 3", "Electric", 2023,
                "Electric", "Automatic", 5, "KA-01-EQ-1234", 4500.00,
                "Bangalore", "Sleek and eco-friendly electric sedan with Autopilot feature.",
                "Available", "https://images.unsplash.com/photo-1560958089-b8a1929cea89?w=800&auto=format&fit=crop&q=80",
                None, None
            ),
            (
                "v2", actual_owner_id, "BMW", "X5", "SUV", 2022,
                "Petrol", "Automatic", 7, "KA-05-MH-9999", 6500.00,
                "Mumbai", "Luxury SUV with panoramic sunroof and premium audio system.",
                "Available", "https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800&auto=format&fit=crop&q=80",
                None, None
            ),
            (
                "v3", actual_owner_id, "Hyundai", "Creta", "SUV", 2023,
                "Diesel", "Manual", 5, "DL-03-CC-4321", 2500.00,
                "Delhi", "Reliable city SUV with great fuel economy and smooth ride.",
                "Available", "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800&auto=format&fit=crop&q=80",
                None, None
            )
        ]
        cursor.executemany(
            """INSERT INTO vehicles (id, owner_id, brand, model, type, year, fuel_type, transmission, seats, reg_no, price, location, description, status, image_url, document_url, rejection_reason)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            sample_vehicles
        )
        conn.commit()
        print("Seeded sample vehicles into MySQL.")

    cursor.close()
    conn.close()
    print("Database initialization complete.")

if __name__ == '__main__':
    init_database()
