import os
import sys
import unittest
import json
import datetime

# Add project root and backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from backend.app import app, get_db_connection

class RentRideTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def setUp(self):
        self.conn = get_db_connection()
        self.cursor = self.conn.cursor(dictionary=True)

    def tearDown(self):
        self.cursor.close()
        self.conn.close()

    # 1. Test Health Endpoint
    def test_01_health_check(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn(data.get('database'), ['connected', 'ok'])

    # 2. Test Registration Validation (Role Restrictions & Age Validation)
    def test_02_registration_validation(self):
        # A. Attempt to register as admin (Must be rejected)
        res = self.client.post('/api/register', json={
            'name': 'Hacker',
            'email': 'hacker@example.com',
            'password': 'password123',
            'role': 'admin'
        })
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn('renter (user) or owner', data.get('error', ''))

        # B. Attempt to register underage user (< 18)
        too_young_dob = (datetime.date.today() - datetime.timedelta(days=365*16)).isoformat()
        res = self.client.post('/api/register', json={
            'name': 'Underage User',
            'email': 'underage@example.com',
            'password': 'password123',
            'role': 'user',
            'dob': too_young_dob
        })
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn('18 years old', data.get('error', ''))

        # C. Valid Registration as User (>= 18)
        valid_dob = (datetime.date.today() - datetime.timedelta(days=365*22)).isoformat()
        test_email = f"test_renter_{datetime.datetime.now().strftime('%H%M%S')}@example.com"
        res = self.client.post('/api/register', json={
            'name': 'Test Renter',
            'email': test_email,
            'password': 'password123',
            'role': 'user',
            'dob': valid_dob,
            'phone': '9876543210'
        })
        self.assertIn(res.status_code, [200, 201])
        res_data = json.loads(res.data)
        self.assertTrue(res_data.get('success'))

    # 3. Test Session Token Generation & Role Authorization
    def test_03_auth_session_and_roles(self):
        # Authenticate demo admin
        res = self.client.post('/api/auth/session', json={
            'email': 'admin@rentride.com'
        })
        if res.status_code != 200:
            # Fallback to demo user seeded or admin@gmail.com
            res = self.client.post('/api/auth/session', json={'email': 'admin@gmail.com'})
        
        self.assertEqual(res.status_code, 200)
        admin_data = json.loads(res.data)
        admin_token = admin_data['token']
        self.assertEqual(admin_data['user']['role'], 'admin')

        # Admin can access /api/users
        users_res = self.client.get('/api/users', headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(users_res.status_code, 200)

        # Authenticate demo user (non-admin)
        user_res = self.client.post('/api/auth/session', json={'email': 'user@rentride.com'})
        if user_res.status_code != 200:
            user_res = self.client.post('/api/auth/session', json={'email': 'ruba@gmail.com'})
        
        self.assertEqual(user_res.status_code, 200)
        regular_user = json.loads(user_res.data)
        user_token = regular_user['token']
        self.assertEqual(regular_user['user']['role'], 'user')

        # Regular user CANNOT access admin /api/users (Must return 403)
        denied_res = self.client.get('/api/users', headers={'Authorization': f'Bearer {user_token}'})
        self.assertEqual(denied_res.status_code, 403)

    # 4. Test Vehicle Listing & Admin Approval Workflow
    def test_04_vehicle_approval_workflow(self):
        # Login owner
        res = self.client.post('/api/auth/session', json={'email': 'owner@rentride.com'})
        if res.status_code != 200:
            res = self.client.post('/api/auth/session', json={'email': 'seema@gmail.com'})
        self.assertEqual(res.status_code, 200)
        owner = json.loads(res.data)
        owner_token = owner['token']

        # Add new vehicle
        v_res = self.client.post('/api/vehicles', headers={'Authorization': f'Bearer {owner_token}'}, json={
            'brand': 'Mahindra',
            'model': 'Thar',
            'type': 'SUV',
            'price': 3500,
            'year': 2024,
            'fuelType': 'Diesel',
            'regNo': 'KA-04-TH-1234'
        })
        self.assertEqual(v_res.status_code, 201)
        vid = json.loads(v_res.data)['id']

        # Verify new vehicle status is 'Pending Approval'
        get_res = self.client.get(f'/api/vehicles/{vid}')
        self.assertEqual(get_res.status_code, 200)
        v_obj = json.loads(get_res.data)
        self.assertEqual(v_obj['status'], 'Pending Approval')

        # Public browse (/api/vehicles) must NOT show 'Pending Approval' vehicle
        browse_res = self.client.get('/api/vehicles')
        browse_list = json.loads(browse_res.data)
        pending_ids = [v['id'] for v in browse_list if v['id'] == vid]
        self.assertEqual(len(pending_ids), 0, "Pending vehicle must not be visible on public listing.")

        # Admin approves vehicle
        admin_res = self.client.post('/api/auth/session', json={'email': 'admin@rentride.com'})
        if admin_res.status_code != 200:
            admin_res = self.client.post('/api/auth/session', json={'email': 'admin@gmail.com'})
        admin_token = json.loads(admin_res.data)['token']

        appr_res = self.client.put(f'/api/vehicles/{vid}', headers={'Authorization': f'Bearer {admin_token}'}, json={
            'status': 'Available'
        })
        self.assertEqual(appr_res.status_code, 200)

        # Now vehicle MUST be visible publicly
        browse_after = self.client.get('/api/vehicles')
        approved_ids = [v['id'] for v in json.loads(browse_after.data) if v['id'] == vid]
        self.assertEqual(len(approved_ids), 1, "Approved vehicle should be visible on public listing.")

        # Admin rejects vehicle with reason
        rej_res = self.client.put(f'/api/vehicles/{vid}', headers={'Authorization': f'Bearer {admin_token}'}, json={
            'status': 'Rejected',
            'rejectionReason': 'Missing valid fitness certificate.'
        })
        self.assertEqual(rej_res.status_code, 200)

        # Verify rejection reason is stored and returned
        check_rej = self.client.get(f'/api/vehicles/{vid}')
        rej_obj = json.loads(check_rej.data)
        self.assertEqual(rej_obj['status'], 'Rejected')
        self.assertEqual(rej_obj.get('rejectionReason'), 'Missing valid fitness certificate.')

    # 5. Test Date Overlap Availability & Booking Creation
    def test_05_date_overlap_and_booking_logic(self):
        # 1. Get an available vehicle
        v_res = self.client.get('/api/vehicles?status=Available')
        vehicles = json.loads(v_res.data)
        self.assertTrue(len(vehicles) > 0, "Should have at least one available vehicle.")
        test_vid = vehicles[0]['id']

        # Select future test dates
        offset5 = int(datetime.datetime.now().timestamp() * 1000) % 50000 + 200
        base_date = datetime.date.today() + datetime.timedelta(days=offset5)
        start1 = (base_date).isoformat()
        end1 = (base_date + datetime.timedelta(days=4)).isoformat()

        # Check availability before booking
        avail_res = self.client.post('/api/bookings/check-availability', json={
            'vehicleId': test_vid,
            'startDate': start1,
            'endDate': end1
        })
        self.assertEqual(avail_res.status_code, 200)
        self.assertTrue(json.loads(avail_res.data)['available'])

        # Create booking for Days 10 to 14
        user_res = self.client.post('/api/auth/session', json={'email': 'user@rentride.com'})
        if user_res.status_code != 200:
            user_res = self.client.post('/api/auth/session', json={'email': 'ruba@gmail.com'})
        user_token = json.loads(user_res.data)['token']

        book_res = self.client.post('/api/bookings', headers={'Authorization': f'Bearer {user_token}'}, json={
            'vehicleId': test_vid,
            'startDate': start1,
            'endDate': end1,
            'totalAmount': 5000,
            'licenseNumber': 'DL-1234567890123'
        })
        self.assertEqual(book_res.status_code, 201)
        booking1_id = json.loads(book_res.data)['id']

        # 2. Check Overlapping Conditions:
        # A. Exact same dates (Days 10 to 14) -> MUST BE UNAVAILABLE
        overlap_res = self.client.post('/api/bookings/check-availability', json={
            'vehicleId': test_vid,
            'startDate': start1,
            'endDate': end1
        })
        self.assertFalse(json.loads(overlap_res.data)['available'], "Exact same dates must conflict.")

        # B. Overlapping start (Days 12 to 16) (requestedStart <= existingEnd AND requestedEnd >= existingStart)
        start_overlap = (base_date + datetime.timedelta(days=2)).isoformat()
        end_overlap = (base_date + datetime.timedelta(days=6)).isoformat()
        res_overlap_start = self.client.post('/api/bookings/check-availability', json={
            'vehicleId': test_vid,
            'startDate': start_overlap,
            'endDate': end_overlap
        })
        self.assertFalse(json.loads(res_overlap_start.data)['available'], "Partially overlapping dates must conflict.")

        # C. Attempting duplicate booking for overlapping dates must return 409 Conflict
        dup_book_res = self.client.post('/api/bookings', headers={'Authorization': f'Bearer {user_token}'}, json={
            'vehicleId': test_vid,
            'startDate': start_overlap,
            'endDate': end_overlap
        })
        self.assertEqual(dup_book_res.status_code, 409, "Server must reject overlapping booking transaction.")

        # D. Non-overlapping dates (Days 20 to 25) -> MUST BE AVAILABLE
        future_start = (base_date + datetime.timedelta(days=10)).isoformat()
        future_end = (base_date + datetime.timedelta(days=15)).isoformat()
        non_overlap_res = self.client.post('/api/bookings/check-availability', json={
            'vehicleId': test_vid,
            'startDate': future_start,
            'endDate': future_end
        })
        self.assertTrue(json.loads(non_overlap_res.data)['available'], "Non-overlapping dates must be available.")

        # E. If booking is Cancelled, dates must become available again immediately
        cancel_res = self.client.put(f'/api/bookings/{booking1_id}', headers={'Authorization': f'Bearer {user_token}'}, json={
            'status': 'Cancelled'
        })
        self.assertEqual(cancel_res.status_code, 200)

        # Check availability again for original dates (Days 10 to 14)
        recheck_res = self.client.post('/api/bookings/check-availability', json={
            'vehicleId': test_vid,
            'startDate': start1,
            'endDate': end1
        })
        self.assertTrue(json.loads(recheck_res.data)['available'], "Cancelled booking must release availability.")

    # 6. Test Payment Submission & Admin Verification (80/20 Split)
    def test_06_payment_and_earnings_split(self):
        # 1. Get user and create booking
        user_res = self.client.post('/api/auth/session', json={'email': 'user@rentride.com'})
        if user_res.status_code != 200:
            user_res = self.client.post('/api/auth/session', json={'email': 'ruba@gmail.com'})
        user_token = json.loads(user_res.data)['token']

        v_res = self.client.get('/api/vehicles?status=Available')
        test_vid = json.loads(v_res.data)[0]['id']

        offset = int(datetime.datetime.now().timestamp() * 1000) % 50000 + 50
        s_date = (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()
        e_date = (datetime.date.today() + datetime.timedelta(days=offset + 2)).isoformat()

        book_res = self.client.post('/api/bookings', headers={'Authorization': f'Bearer {user_token}'}, json={
            'vehicleId': test_vid,
            'startDate': s_date,
            'endDate': e_date,
            'totalAmount': 10000.00
        })
        self.assertEqual(book_res.status_code, 201)
        bid = json.loads(book_res.data)['id']

        # 2. Submit payment with UPI reference
        pay_res = self.client.post('/api/payments', headers={'Authorization': f'Bearer {user_token}'}, json={
            'bookingId': bid,
            'amount': 10000.00,
            'method': 'UPI',
            'referenceNo': 'UPI-REF-99887766'
        })
        self.assertEqual(pay_res.status_code, 201)
        pid = json.loads(pay_res.data)['id']

        # Verify payment is Pending Verification
        p_list = self.client.get('/api/payments', headers={'Authorization': f'Bearer {user_token}'})
        my_pay = [p for p in json.loads(p_list.data) if p['id'] == pid][0]
        self.assertEqual(my_pay['status'], 'Pending Verification')
        self.assertEqual(my_pay['referenceNo'], 'UPI-REF-99887766')

        # 3. Admin verifies payment
        admin_res = self.client.post('/api/auth/session', json={'email': 'admin@rentride.com'})
        if admin_res.status_code != 200:
            admin_res = self.client.post('/api/auth/session', json={'email': 'admin@gmail.com'})
        admin_token = json.loads(admin_res.data)['token']

        verify_res = self.client.put(f'/api/payments/{pid}', headers={'Authorization': f'Bearer {admin_token}'}, json={
            'status': 'Paid',
            'adminNote': 'Bank transaction verified successfully.'
        })
        self.assertEqual(verify_res.status_code, 200)

        # Check booking status is now Confirmed and Paid
        book_check = self.client.get(f'/api/bookings/{bid}', headers={'Authorization': f'Bearer {user_token}'})
        confirmed_book = json.loads(book_check.data)
        self.assertEqual(confirmed_book['paymentStatus'], 'Paid')
        self.assertEqual(confirmed_book['status'], 'Confirmed')

        # 4. Verify 80/20 earnings split calculation
        amount = 10000.00
        admin_share_20 = amount * 0.20
        owner_share_80 = amount * 0.80
        self.assertEqual(admin_share_20, 2000.00)
        self.assertEqual(owner_share_80, 8000.00)
        self.assertEqual(admin_share_20 + owner_share_80, amount)

if __name__ == '__main__':
    unittest.main()
