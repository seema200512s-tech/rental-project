import os
import sys
import unittest
import json
import uuid
import datetime

# Add project root and backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.app import app, get_db_connection, generate_jwt_token

class GooglePayUPIPaymentTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

        # Create test users and vehicle
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cls.renter_id = f"renter-gpay-{uuid.uuid4().hex[:8]}"
        cls.renter_email = f"renter_gpay_{uuid.uuid4().hex[:6]}@test.com"
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash, role, phone, active)
            VALUES (%s, %s, %s, 'hash', 'user', '9876543210', 1)
        """, (cls.renter_id, 'Test GPay Renter', cls.renter_email))

        cls.owner_id = f"owner-gpay-{uuid.uuid4().hex[:8]}"
        cls.owner_email = f"owner_gpay_{uuid.uuid4().hex[:6]}@test.com"
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash, role, phone, active)
            VALUES (%s, %s, %s, 'hash', 'owner', '9876543211', 1)
        """, (cls.owner_id, 'Test GPay Owner', cls.owner_email))

        cls.admin_id = f"admin-gpay-{uuid.uuid4().hex[:8]}"
        cls.admin_email = f"admin_gpay_{uuid.uuid4().hex[:6]}@test.com"
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash, role, phone, active)
            VALUES (%s, %s, %s, 'hash', 'admin', '9876543212', 1)
        """, (cls.admin_id, 'Test GPay Admin', cls.admin_email))

        cls.other_user_id = f"other-gpay-{uuid.uuid4().hex[:8]}"
        cls.other_user_email = f"other_gpay_{uuid.uuid4().hex[:6]}@test.com"
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash, role, phone, active)
            VALUES (%s, %s, %s, 'hash', 'user', '9876543213', 1)
        """, (cls.other_user_id, 'Other User', cls.other_user_email))

        cls.vehicle_id = f"veh-gpay-{uuid.uuid4().hex[:8]}"
        cursor.execute("""
            INSERT INTO vehicles (id, owner_id, brand, model, year, type, transmission, fuel_type, seats, price, location, status)
            VALUES (%s, %s, 'Toyota', 'Fortuner', 2024, 'SUV', 'Automatic', 'Diesel', 7, 3500.00, 'Bangalore', 'Available')
        """, (cls.vehicle_id, cls.owner_id))

        conn.commit()
        cursor.close()
        conn.close()

        cls.renter_token = generate_jwt_token(cls.renter_id, 'user', cls.renter_email)
        cls.admin_token = generate_jwt_token(cls.admin_id, 'admin', cls.admin_email)

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM payments WHERE user_id = %s", (cls.renter_id,))
        cursor.execute("DELETE FROM bookings WHERE user_id = %s", (cls.renter_id,))
        cursor.execute("DELETE FROM vehicles WHERE id = %s", (cls.vehicle_id,))
        cursor.execute("DELETE FROM users WHERE id IN (%s, %s)", (cls.renter_id, cls.owner_id))
        conn.commit()
        cursor.close()
        conn.close()

    def setUp(self):
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor(dictionary=True, buffered=True)

    def tearDown(self):
        self.cursor.close()
        self.conn.close()

    def create_test_booking(self, status='Pending', total_amount=7000.00, days=2, start_offset=10):
        start_date = datetime.date.today() + datetime.timedelta(days=start_offset)
        end_date = start_date + datetime.timedelta(days=days - 1)
        bid = f"book-gpay-{uuid.uuid4().hex[:8]}"

        self.cursor.execute("""
            INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
        """, (bid, self.vehicle_id, self.renter_id, self.owner_id, start_date, end_date, status, total_amount, 3500.00, days))
        self.conn.commit()
        return bid, start_date, end_date

    # 1. Unauthenticated request must return 401
    def test_01_unauthenticated_payment(self):
        res = self.client.post('/api/payments', json={'bookingId': 'any-id', 'referenceNo': '123456789012'})
        self.assertEqual(res.status_code, 401)

    # 2. Missing bookingId must return 400
    def test_02_missing_booking_id(self):
        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'referenceNo': '123456789012'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('Missing booking ID', json.loads(res.data).get('error', ''))

    # 3. Missing reference number must return 400
    def test_03_missing_reference_no(self):
        bid, _, _ = self.create_test_booking()
        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': bid, 'referenceNo': ''})
        self.assertEqual(res.status_code, 400)
        self.assertIn('reference number is required', json.loads(res.data).get('error', '').lower())

    # 4. Short reference number must return 400
    def test_04_short_reference_no(self):
        bid, _, _ = self.create_test_booking(start_offset=20)
        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': bid, 'referenceNo': '12'})
        self.assertEqual(res.status_code, 400)

    # 5. Cannot pay for another user's booking
    def test_05_unauthorized_booking_access(self):
        other_bid = f"book-other-{uuid.uuid4().hex[:8]}"
        self.cursor.execute("""
            INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status)
            VALUES (%s, %s, %s, %s, '2026-11-01', '2026-11-03', 'Pending', 7000.00, 3500.00, 2, 'Pending')
        """, (other_bid, self.vehicle_id, self.other_user_id, self.owner_id))
        self.conn.commit()

        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': other_bid, 'referenceNo': '123456789012'})
        self.assertEqual(res.status_code, 403)

    # 6. Cannot pay for cancelled or rejected bookings
    def test_06_cancelled_booking_rejected(self):
        bid, _, _ = self.create_test_booking(status='Cancelled', start_offset=30)
        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': bid, 'referenceNo': '123456789012'})
        self.assertEqual(res.status_code, 400)

    # 7. Successful payment confirmation sets status='Pending Verification' and uses MySQL amount
    def test_07_successful_payment_confirmation(self):
        bid, _, _ = self.create_test_booking(total_amount=7000.00, start_offset=40)
        utr = f"GPAY-{uuid.uuid4().hex[:10].upper()}"

        # Attacker sends fake amount ₹1.00 - server MUST ignore it and record ₹7000.00
        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={
                                   'bookingId': bid,
                                   'amount': 1.00,
                                   'referenceNo': utr,
                                   'method': 'Google Pay UPI',
                                   'paymentProof': '/static/uploads/proof_test.png'
                               })
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'Pending Verification')
        self.assertEqual(data['amount'], 7000.00)
        self.assertEqual(data['referenceNo'], utr)

        # Verify DB booking payment_status is 'Pending Verification' (NOT 'Paid')
        self.cursor.execute("SELECT status, payment_status FROM bookings WHERE id = %s", (bid,))
        b_row = self.cursor.fetchone()
        self.assertEqual(b_row['payment_status'], 'Pending Verification')
        self.assertNotEqual(b_row['payment_status'], 'Paid')

        # Verify payment record
        self.cursor.execute("SELECT * FROM payments WHERE id = %s", (data['id'],))
        p_row = self.cursor.fetchone()
        self.assertEqual(p_row['status'], 'Pending Verification')
        self.assertEqual(float(p_row['amount']), 7000.00)
        self.assertEqual(p_row['reference_no'], utr)

    # 8. Re-submitting payment for same booking updates existing pending confirmation
    def test_08_resubmission_updates_existing_pending(self):
        bid, _, _ = self.create_test_booking(total_amount=7000.00, start_offset=60)
        utr1 = f"GPAY-{uuid.uuid4().hex[:10].upper()}"
        utr2 = f"GPAY-{uuid.uuid4().hex[:10].upper()}"

        res1 = self.client.post('/api/payments',
                                headers={'Authorization': f'Bearer {self.renter_token}'},
                                json={'bookingId': bid, 'referenceNo': utr1})
        self.assertEqual(res1.status_code, 201)
        pid1 = json.loads(res1.data)['id']

        # User updates their reference number / proof
        res2 = self.client.post('/api/payments',
                                headers={'Authorization': f'Bearer {self.renter_token}'},
                                json={'bookingId': bid, 'referenceNo': utr2, 'paymentProof': '/static/uploads/proof2.png'})
        self.assertEqual(res2.status_code, 201)
        pid2 = json.loads(res2.data)['id']
        self.assertEqual(pid1, pid2) # Same pending record updated

        # Verify only 1 payment row exists for this booking
        self.cursor.execute("SELECT COUNT(*) AS cnt FROM payments WHERE booking_id = %s", (bid,))
        count = self.cursor.fetchone()['cnt']
        self.assertEqual(count, 1)

    # 9. Admin verifies payment -> booking status becomes Confirmed, payment becomes Paid
    def test_09_admin_verification_flow(self):
        bid, _, _ = self.create_test_booking(total_amount=7000.00, start_offset=80)
        utr = f"GPAY-{uuid.uuid4().hex[:10].upper()}"

        res = self.client.post('/api/payments',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': bid, 'referenceNo': utr})
        self.assertEqual(res.status_code, 201)
        pid = json.loads(res.data)['id']

        # Admin approves
        approve_res = self.client.put(f"/api/payments/{pid}",
                                      headers={'Authorization': f'Bearer {self.admin_token}'},
                                      json={'status': 'Paid', 'adminNote': 'Verified in GPay bank statement'})
        self.assertEqual(approve_res.status_code, 200)

        # Booking is now Confirmed and Paid
        self.cursor.execute("SELECT status, payment_status FROM bookings WHERE id = %s", (bid,))
        b_verified = self.cursor.fetchone()
        self.assertEqual(b_verified['status'], 'Confirmed')
        self.assertEqual(b_verified['payment_status'], 'Paid')

if __name__ == '__main__':
    unittest.main()
