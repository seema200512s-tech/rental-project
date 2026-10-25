import os
import sys
import unittest
import json
import uuid
import datetime
import hmac
import hashlib
from unittest.mock import MagicMock, patch

# Add project root and backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.app import app, get_db_connection, generate_jwt_token

class PaymentGatewayTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['RAZORPAY_KEY_ID'] = 'rzp_test_mock_key_id'
        app.config['RAZORPAY_KEY_SECRET'] = 'mock_secret_key_123456789'
        app.config['RAZORPAY_WEBHOOK_SECRET'] = 'mock_webhook_secret_987654321'
        cls.client = app.test_client()

        # Create or fetch test users in MySQL
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Test Renter
        cls.renter_id = f"renter-test-{uuid.uuid4().hex[:8]}"
        cls.renter_email = f"renter_{uuid.uuid4().hex[:6]}@test.com"
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash, role, phone, active)
            VALUES (%s, %s, %s, 'hash', 'user', '9876543210', 1)
        """, (cls.renter_id, 'Test Renter', cls.renter_email))

        # Test Owner
        cls.owner_id = f"owner-test-{uuid.uuid4().hex[:8]}"
        cls.owner_email = f"owner_{uuid.uuid4().hex[:6]}@test.com"
        cursor.execute("""
            INSERT INTO users (id, name, email, password_hash, role, phone, active)
            VALUES (%s, %s, %s, 'hash', 'owner', '9876543211', 1)
        """, (cls.owner_id, 'Test Owner', cls.owner_email))

        # Test Vehicle
        cls.vehicle_id = f"veh-test-{uuid.uuid4().hex[:8]}"
        cursor.execute("""
            INSERT INTO vehicles (id, owner_id, brand, model, year, type, transmission, fuel_type, seats, price, location, status)
            VALUES (%s, %s, 'Hyundai', 'Creta', 2023, 'SUV', 'Automatic', 'Petrol', 5, 2000.00, 'Mumbai', 'Available')
        """, (cls.vehicle_id, cls.owner_id))

        conn.commit()
        cursor.close()
        conn.close()

        cls.renter_token = generate_jwt_token(cls.renter_id, 'user', cls.renter_email)

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
        self.cursor = self.conn.cursor(dictionary=True)

    def tearDown(self):
        self.cursor.close()
        self.conn.close()

    def create_test_booking(self, status='Pending', total_amount=4000.00, days=2, start_offset=10):
        start_date = datetime.date.today() + datetime.timedelta(days=start_offset)
        end_date = start_date + datetime.timedelta(days=days - 1)
        bid = f"book-{uuid.uuid4().hex[:8]}"

        self.cursor.execute("""
            INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
        """, (bid, self.vehicle_id, self.renter_id, self.owner_id, start_date, end_date, status, total_amount, 2000.00, days))
        self.conn.commit()
        return bid, start_date, end_date

    # 1. Unauthenticated request must be rejected
    def test_01_create_order_unauthenticated(self):
        res = self.client.post('/api/payments/create-order', json={'bookingId': 'any-id'})
        self.assertEqual(res.status_code, 401)

    # 2. Missing booking ID must return 400
    def test_02_create_order_missing_id(self):
        res = self.client.post('/api/payments/create-order',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('Missing booking ID', json.loads(res.data).get('error', ''))

    # 3. Create order uses actual MySQL amount and ignores any frontend tampering
    @patch('backend.app.get_razorpay_client')
    def test_03_create_order_trusts_only_mysql_amount(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.order.create.return_value = {
            'id': 'order_mock_test_12345',
            'amount': 400000,
            'currency': 'INR',
            'status': 'created'
        }
        mock_client_factory.return_value = mock_client

        bid, _, _ = self.create_test_booking(total_amount=4000.00)

        # Attacker tries to send fake amount: ₹1.00
        res = self.client.post('/api/payments/create-order',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': bid, 'amount': 1.00})

        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data['orderId'], 'order_mock_test_12345')
        self.assertEqual(data['amountInRupees'], 4000.00)
        self.assertEqual(data['amount'], 400000) # In paise

        # Verify mock received 400000 paise (₹4000.00), not ₹1.00
        mock_client.order.create.assert_called_once()
        create_call_args = mock_client.order.create.call_args[1]['data']
        self.assertEqual(create_call_args['amount'], 400000)

    # 4. Overlapping confirmed booking blocks payment order
    def test_04_create_order_detects_overlapping_booking(self):
        bid1, s1, e1 = self.create_test_booking(status='Pending', start_offset=30)
        # Create an existing confirmed booking overlapping the same dates
        bid_conflict = f"conflict-{uuid.uuid4().hex[:8]}"
        self.cursor.execute("""
            INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Confirmed', 4000.00, 2000.00, 2, 'Paid')
        """, (bid_conflict, self.vehicle_id, self.renter_id, self.owner_id, s1, e1))
        self.conn.commit()

        res = self.client.post('/api/payments/create-order',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={'bookingId': bid1})
        self.assertEqual(res.status_code, 409)
        self.assertIn('already booked', json.loads(res.data).get('error', '').lower())

    # 5. Payment signature verification fails on tampered/invalid signature
    @patch('backend.app.get_razorpay_client')
    def test_05_verify_payment_invalid_signature(self, mock_client_factory):
        import razorpay.errors
        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.side_effect = razorpay.errors.SignatureVerificationError("Invalid signature")
        mock_client_factory.return_value = mock_client

        bid, _, _ = self.create_test_booking(start_offset=50)

        res = self.client.post('/api/payments/verify',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={
                                   'bookingId': bid,
                                   'razorpay_order_id': 'order_fake_123',
                                   'razorpay_payment_id': 'pay_fake_456',
                                   'razorpay_signature': 'invalid_signature_hex'
                               })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid payment signature', json.loads(res.data).get('error', ''))

    # 6. Payment signature verified successfully -> Booking Confirmed & Payment Paid
    @patch('backend.app.get_razorpay_client')
    def test_06_verify_payment_success_and_confirmation(self, mock_client_factory):
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        secret = app.config['RAZORPAY_KEY_SECRET']
        valid_signature = hmac.new(secret.encode('utf-8'), f"{order_id}|{payment_id}".encode('utf-8'), hashlib.sha256).hexdigest()

        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 400000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_client_factory.return_value = mock_client

        bid, _, _ = self.create_test_booking(total_amount=4000.00, start_offset=70)

        res = self.client.post('/api/payments/verify',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={
                                   'bookingId': bid,
                                   'razorpay_order_id': order_id,
                                   'razorpay_payment_id': payment_id,
                                   'razorpay_signature': valid_signature
                               })

        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'Confirmed')
        self.assertEqual(data['paymentId'], payment_id)
        self.assertEqual(data['bookingId'], bid)

        # Verify database state
        self.cursor.execute("SELECT status, payment_status, razorpay_order_id FROM bookings WHERE id = %s", (bid,))
        updated_b = self.cursor.fetchone()
        self.assertEqual(updated_b['status'], 'Confirmed')
        self.assertEqual(updated_b['payment_status'], 'Paid')

        self.cursor.execute("SELECT * FROM payments WHERE razorpay_payment_id = %s", (payment_id,))
        pmt = self.cursor.fetchone()
        self.assertIsNotNone(pmt)
        self.assertEqual(pmt['status'], 'Paid')
        self.assertEqual(pmt['method'], 'UPI_RAZORPAY')

    # 7. Duplicate payment verification submission is idempotent
    @patch('backend.app.get_razorpay_client')
    def test_07_verify_payment_duplicate_idempotency(self, mock_client_factory):
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        secret = app.config['RAZORPAY_KEY_SECRET']
        valid_signature = hmac.new(secret.encode('utf-8'), f"{order_id}|{payment_id}".encode('utf-8'), hashlib.sha256).hexdigest()

        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 400000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_client_factory.return_value = mock_client

        bid, _, _ = self.create_test_booking(total_amount=4000.00, start_offset=90)

        # 1st call
        res1 = self.client.post('/api/payments/verify',
                                headers={'Authorization': f'Bearer {self.renter_token}'},
                                json={'bookingId': bid, 'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': valid_signature})
        self.assertEqual(res1.status_code, 200)

        # 2nd call with identical payment ID
        res2 = self.client.post('/api/payments/verify',
                                headers={'Authorization': f'Bearer {self.renter_token}'},
                                json={'bookingId': bid, 'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id, 'razorpay_signature': valid_signature})
        self.assertEqual(res2.status_code, 200)
        data2 = json.loads(res2.data)
        self.assertTrue(data2.get('alreadyProcessed'))

        # Verify only 1 payment row exists for this payment_id
        self.cursor.execute("SELECT COUNT(*) AS cnt FROM payments WHERE razorpay_payment_id = %s", (payment_id,))
        count = self.cursor.fetchone()['cnt']
        self.assertEqual(count, 1)

    # 8. Webhook rejects invalid signature
    @patch('backend.app.get_razorpay_client')
    def test_08_webhook_invalid_signature(self, mock_client_factory):
        import razorpay.errors
        mock_client = MagicMock()
        mock_client.utility.verify_webhook_signature.side_effect = razorpay.errors.SignatureVerificationError("Invalid webhook signature")
        mock_client_factory.return_value = mock_client

        res = self.client.post('/api/payments/webhook',
                               data=json.dumps({'event': 'payment.captured'}),
                               headers={
                                   'Content-Type': 'application/json',
                                   'X-Razorpay-Signature': 'bogus_signature'
                               })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid webhook signature', json.loads(res.data).get('error', ''))

    # 9. Webhook processes payment.captured and guarantees idempotency
    @patch('backend.app.get_razorpay_client')
    def test_09_webhook_captured_and_idempotency(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.utility.verify_webhook_signature.return_value = True
        mock_client_factory.return_value = mock_client

        bid, _, _ = self.create_test_booking(total_amount=4000.00, start_offset=120)
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"

        # Set razorpay_order_id on booking
        self.cursor.execute("UPDATE bookings SET razorpay_order_id = %s WHERE id = %s", (order_id, bid))
        self.conn.commit()

        webhook_body = {
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': payment_id,
                        'order_id': order_id,
                        'amount': 400000,
                        'currency': 'INR',
                        'notes': {
                            'booking_id': bid
                        }
                    }
                }
            }
        }

        # 1st webhook call
        res1 = self.client.post('/api/payments/webhook',
                                data=json.dumps(webhook_body),
                                headers={
                                    'Content-Type': 'application/json',
                                    'X-Razorpay-Signature': 'valid_sig'
                                })
        self.assertEqual(res1.status_code, 200)

        # Verify DB updated
        self.cursor.execute("SELECT status, payment_status FROM bookings WHERE id = %s", (bid,))
        b_state = self.cursor.fetchone()
        self.assertEqual(b_state['status'], 'Confirmed')
        self.assertEqual(b_state['payment_status'], 'Paid')

        # 2nd webhook call (duplicate delivery from gateway retry)
        res2 = self.client.post('/api/payments/webhook',
                                data=json.dumps(webhook_body),
                                headers={
                                    'Content-Type': 'application/json',
                                    'X-Razorpay-Signature': 'valid_sig'
                                })
        self.assertEqual(res2.status_code, 200)

        # Still exactly 1 payment record
        self.cursor.execute("SELECT COUNT(*) AS cnt FROM payments WHERE razorpay_payment_id = %s", (payment_id,))
        count = self.cursor.fetchone()['cnt']
        self.assertEqual(count, 1)

    # 10. Webhook records failed payment attempts
    @patch('backend.app.get_razorpay_client')
    def test_10_webhook_payment_failed(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client.utility.verify_webhook_signature.return_value = True
        mock_client_factory.return_value = mock_client

        bid, _, _ = self.create_test_booking(total_amount=4000.00, start_offset=140)
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_failed_{uuid.uuid4().hex[:12]}"

        webhook_body = {
            'event': 'payment.failed',
            'payload': {
                'payment': {
                    'entity': {
                        'id': payment_id,
                        'order_id': order_id,
                        'amount': 400000,
                        'currency': 'INR',
                        'notes': {
                            'booking_id': bid
                        }
                    }
                }
            }
        }

        res = self.client.post('/api/payments/webhook',
                               data=json.dumps(webhook_body),
                               headers={
                                   'Content-Type': 'application/json',
                                   'X-Razorpay-Signature': 'valid_sig'
                               })
        self.assertEqual(res.status_code, 200)

        # Verify failed payment row was recorded
        self.cursor.execute("SELECT status FROM payments WHERE razorpay_payment_id = %s", (payment_id,))
        pmt = self.cursor.fetchone()
        self.assertIsNotNone(pmt)
        self.assertEqual(pmt['status'], 'Failed')

    # 11. Verification blocks overlapping confirmed bookings if another booking was confirmed in between
    @patch('backend.app.get_razorpay_client')
    def test_11_verify_payment_blocks_overlap_race_condition(self, mock_client_factory):
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        secret = app.config['RAZORPAY_KEY_SECRET']
        valid_signature = hmac.new(secret.encode('utf-8'), f"{order_id}|{payment_id}".encode('utf-8'), hashlib.sha256).hexdigest()

        mock_client = MagicMock()
        mock_client.utility.verify_payment_signature.return_value = True
        mock_client.payment.fetch.return_value = {
            'id': payment_id,
            'order_id': order_id,
            'amount': 400000,
            'currency': 'INR',
            'status': 'captured'
        }
        mock_client_factory.return_value = mock_client

        bid, s, e = self.create_test_booking(total_amount=4000.00, start_offset=160)

        # Another booking gets confirmed on the same dates before user verifies
        bid_other = f"other-{uuid.uuid4().hex[:8]}"
        self.cursor.execute("""
            INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Confirmed', 4000.00, 2000.00, 2, 'Paid')
        """, (bid_other, self.vehicle_id, self.renter_id, self.owner_id, s, e))
        self.conn.commit()

        res = self.client.post('/api/payments/verify',
                               headers={'Authorization': f'Bearer {self.renter_token}'},
                               json={
                                   'bookingId': bid,
                                   'razorpay_order_id': order_id,
                                   'razorpay_payment_id': payment_id,
                                   'razorpay_signature': valid_signature
                               })
        self.assertEqual(res.status_code, 409)
        self.assertIn('already booked', json.loads(res.data).get('error', '').lower())

if __name__ == '__main__':
    unittest.main()

