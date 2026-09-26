import mysql.connector
from werkzeug.security import generate_password_hash
import uuid

def init_database():
    # 1. Connect without database to create rentride DB
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password=''
    )
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS rentride;")
    cursor.close()
    conn.close()

    # 2. Connect to rentride DB
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='rentride'
    )
    cursor = conn.cursor()

    # Create tables
    tables = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            phone VARCHAR(20),
            dob DATE,
            address TEXT,
            role VARCHAR(50) NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            id VARCHAR(255) PRIMARY KEY,
            owner_id VARCHAR(255) NOT NULL,
            brand VARCHAR(100),
            model VARCHAR(100),
            type VARCHAR(50),
            year INT,
            fuel_type VARCHAR(50),
            transmission VARCHAR(50),
            seats INT,
            reg_no VARCHAR(50),
            price DECIMAL(10, 2),
            location VARCHAR(255),
            description TEXT,
            status VARCHAR(50) DEFAULT 'Available',
            image_url VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
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
            total_amount DECIMAL(10, 2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS payments (
            id VARCHAR(255) PRIMARY KEY,
            booking_id VARCHAR(255) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            owner_id VARCHAR(255) NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'Pending Verification',
            method VARCHAR(50) DEFAULT 'UPI',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS favorites (
            user_id VARCHAR(255) NOT NULL,
            vehicle_id VARCHAR(255) NOT NULL,
            PRIMARY KEY (user_id, vehicle_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id VARCHAR(255) PRIMARY KEY,
            vehicle_id VARCHAR(255) NOT NULL,
            booking_id VARCHAR(255) NOT NULL,
            rating INT NOT NULL,
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS maintenance (
            id VARCHAR(255) PRIMARY KEY,
            vehicle_id VARCHAR(255) NOT NULL,
            owner_id VARCHAR(255) NOT NULL,
            description TEXT,
            cost DECIMAL(10, 2),
            status VARCHAR(50) DEFAULT 'Pending',
            date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id VARCHAR(255) PRIMARY KEY,
            recipient_id VARCHAR(255),
            recipient_role VARCHAR(50),
            title VARCHAR(255),
            message TEXT,
            status VARCHAR(50) DEFAULT 'unread',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ]

    for statement in tables:
        cursor.execute(statement)
    conn.commit()

    # Seed default accounts if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        demo_users = [
            (str(uuid.uuid4()), "System Admin", "admin@rentride.com", generate_password_hash("admin123", method="pbkdf2:sha256"), "9876543210", "1990-01-01", "Admin HQ, City", "admin"),
            (str(uuid.uuid4()), "Vehicle Owner", "owner@rentride.com", generate_password_hash("owner123", method="pbkdf2:sha256"), "9876543211", "1992-05-15", "Owner St, City", "owner"),
            (str(uuid.uuid4()), "Demo User", "user@rentride.com", generate_password_hash("user123", method="pbkdf2:sha256"), "9876543212", "1995-10-20", "User Ave, City", "user")
        ]
        cursor.executemany(
            "INSERT INTO users (id, name, email, password_hash, phone, dob, address, role) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            demo_users
        )
        conn.commit()
        print("Seeded default users (admin@rentride.com / admin123, owner@rentride.com / owner123, user@rentride.com / user123).")

    cursor.close()
    conn.close()
    print("Database initialization complete.")

if __name__ == '__main__':
    init_database()
