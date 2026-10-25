import os
import uuid
import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Configure CORS dynamically
cors_origins_env = os.environ.get('CORS_ORIGINS', '')
allowed_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "https://rental-project-tan.vercel.app"
]
if cors_origins_env:
    for o in cors_origins_env.split(','):
        if o.strip() and o.strip() not in allowed_origins:
            allowed_origins.append(o.strip())

CORS(app, resources={
    r"/*": {
        "origins": allowed_origins,
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Access-Control-Allow-Origin", "Accept"],
        "supports_credentials": True
    }
})

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_db_connection():
    return mysql.connector.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        port=app.config.get('MYSQL_PORT', 3306)
    )

@app.errorhandler(Exception)
def handle_exception(e):
    # Log securely without exposing stack traces or internal DB credentials
    app.logger.error(f"Internal error: {str(e)}")
    return jsonify({'error': 'An internal server error occurred. Please try again later.'}), 500

@app.route('/')
def index():
    return jsonify({
        'status': 'online',
        'service': 'RentRide REST API',
        'version': '1.0.0',
        'health': '/api/health'
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    db_status = "disconnected"
    try:
        conn = get_db_connection()
        if conn.is_connected():
            db_status = "connected"
            conn.close()
    except Exception as e:
        db_status = f"error: {str(e)}"
        
    return jsonify({
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })

def generate_jwt_token(user_id, role, email):
    payload = {
        'uid': user_id,
        'role': role,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7),
        'iat': datetime.datetime.utcnow()
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm="HS256")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        
        if not token:
            return jsonify({'error': 'Authentication token is required.'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            user_id = data['uid']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired. Please log in again.'}), 401
        except Exception:
            return jsonify({'error': 'Invalid authentication token.'}), 401
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users WHERE id = %s", (user_id,))
        current_user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not current_user:
            return jsonify({'error': 'User account not found.'}), 401
        if not current_user.get('active', True):
            return jsonify({'error': 'Your account has been suspended. Please contact administrator.'}), 403
            
        return f(current_user, *args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(current_user, *args, **kwargs):
            if current_user.get('role') not in allowed_roles:
                return jsonify({'error': 'Forbidden: Insufficient privileges for this action.'}), 403
            return f(current_user, *args, **kwargs)
        return wrapper
    return decorator

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ─────────────────────────────────────────────────────────────
# 1. AUTHENTICATION & REGISTRATION
# ─────────────────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    role = (data.get('role') or 'user').strip().lower()
    phone = (data.get('phone') or '').strip()
    dob = data.get('dob')
    address = (data.get('address') or '').strip()
    uid = data.get('uid') or str(uuid.uuid4())
    password = data.get('password')

    if not name or not email:
        return jsonify({'error': 'Name and email are required.'}), 400

    # Never allow registering as admin publicly
    if role not in ['user', 'owner']:
        return jsonify({'error': 'Registration role must be renter (user) or owner.'}), 400

    # Age check (must be at least 18)
    if dob:
        try:
            dob_date = datetime.datetime.strptime(dob, '%Y-%m-%d').date()
            today = datetime.date.today()
            age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
            if age < 18:
                return jsonify({'error': 'You must be at least 18 years old to register.'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid date of birth format. Use YYYY-MM-DD.'}), 400

    password_hash = generate_password_hash(password, method='pbkdf2:sha256') if password else None

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if email already exists
        cursor.execute("SELECT id, email FROM users WHERE email = %s", (email,))
        existing = cursor.fetchone()
        if existing:
            # If already registered with this email, update UID if not set
            cursor.execute("UPDATE users SET id = %s WHERE email = %s", (uid, email))
            conn.commit()
            return jsonify({'success': True, 'uid': uid, 'message': 'Account synchronized successfully.'}), 200

        cursor.execute(
            """INSERT INTO users (id, name, email, password_hash, phone, dob, address, role, active) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)""",
            (uid, name, email, password_hash, phone, dob if dob else None, address, role)
        )
        conn.commit()
        return jsonify({'success': True, 'uid': uid}), 201
    except mysql.connector.IntegrityError:
        return jsonify({'error': 'This email address is already registered.'}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/auth/session', methods=['POST'])
def auth_session():
    data = request.get_json() or {}
    uid = data.get('uid')
    email = (data.get('email') or '').strip().lower()

    if not uid and not email:
        return jsonify({'error': 'Authentication identifier is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Look up by UID
    cursor.execute("SELECT id, name, email, phone, dob, address, role, active FROM users WHERE id = %s", (uid,))
    user = cursor.fetchone()

    # 2. Look up by Email if not found by UID
    if not user and email:
        cursor.execute("SELECT id, name, email, phone, dob, address, role, active FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user and uid:
            # Re-link Firebase UID
            cursor.execute("UPDATE users SET id = %s WHERE email = %s", (uid, email))
            conn.commit()
            user['id'] = uid

    cursor.close()
    conn.close()

    if not user:
        return jsonify({'error': 'User profile not found in system. Please register.'}), 404

    if not user.get('active', True):
        return jsonify({'error': 'Your account has been suspended. Please contact the administrator.'}), 403

    token = generate_jwt_token(user['id'], user['role'], user['email'])
    return jsonify({
        'token': token,
        'user': user
    }), 200

@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user_profile(current_user):
    return jsonify({'user': current_user}), 200

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and user.get('password_hash') and check_password_hash(user['password_hash'], password):
        if not user.get('active', True):
            return jsonify({'error': 'Your account has been suspended.'}), 403
            
        token = generate_jwt_token(user['id'], user['role'], user['email'])
        del user['password_hash']
        return jsonify({'token': token, 'user': user}), 200
        
    return jsonify({'error': 'Invalid email or password.'}), 401

# ─────────────────────────────────────────────────────────────
# 2. USERS MANAGEMENT (Role Protected)
# ─────────────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@token_required
@role_required(['admin'])
def get_users(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    role = request.args.get('role')
    if role:
        cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users WHERE role = %s ORDER BY created_at DESC", (role,))
    else:
        cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users), 200

@app.route('/api/users/<uid>', methods=['GET'])
@token_required
def get_user(current_user, uid):
    # Only Admin or the user themselves can view this profile
    if current_user['role'] != 'admin' and current_user['id'] != uid:
        return jsonify({'error': 'Access denied to this user profile.'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users WHERE id = %s", (uid,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user:
        return jsonify(user), 200
    return jsonify({'error': 'User not found.'}), 404

@app.route('/api/users/<uid>', methods=['PUT'])
@token_required
def update_user(current_user, uid):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()

    is_admin = current_user['role'] == 'admin'
    is_self = current_user['id'] == uid

    if not is_admin and not is_self:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Permission denied.'}), 403

    updates = []
    params = []

    # Fields self or admin can update
    for k in ['name', 'phone', 'address']:
        if k in data:
            updates.append(f"{k} = %s")
            params.append(data[k])

    # Fields only Admin can update
    if is_admin:
        if 'active' in data:
            updates.append("active = %s")
            params.append(bool(data['active']))
        elif 'status' in data:
            updates.append("active = %s")
            params.append(data['status'] == 'Active')
        if 'role' in data and data['role'] in ['user', 'owner', 'admin']:
            updates.append("role = %s")
            params.append(data['role'])

    if updates:
        params.append(uid)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()

    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

# ─────────────────────────────────────────────────────────────
# 3. VEHICLES & LISTINGS
# ─────────────────────────────────────────────────────────────

@app.route('/api/vehicles', methods=['GET'])
def get_vehicles():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    owner_id = request.args.get('ownerId')
    status = request.args.get('status')
    
    query = "SELECT * FROM vehicles WHERE 1=1"
    params = []
    
    if owner_id:
        query += " AND owner_id = %s"
        params.append(owner_id)
        if status:
            query += " AND status = %s"
            params.append(status)
    elif status:
        query += " AND status = %s"
        params.append(status)
    else:
        # If public request without filter, default to only Available vehicles
        query += " AND status = 'Available'"
        
    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    vehicles = cursor.fetchall()
    
    for v in vehicles:
        v['ownerId'] = v.pop('owner_id')
        v['fuelType'] = v.pop('fuel_type')
        v['regNo'] = v.pop('reg_no')
        v['imageUrl'] = v.pop('image_url')
        v['documentUrl'] = v.pop('document_url', None)
        v['rejectionReason'] = v.pop('rejection_reason', None)
        v['price'] = float(v['price']) if v.get('price') is not None else 0.0

    cursor.close()
    conn.close()
    return jsonify(vehicles), 200

@app.route('/api/vehicles/<vid>', methods=['GET'])
def get_vehicle(vid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM vehicles WHERE id = %s", (vid,))
    v = cursor.fetchone()
    cursor.close()
    conn.close()
    if v:
        v['ownerId'] = v.pop('owner_id')
        v['fuelType'] = v.pop('fuel_type')
        v['regNo'] = v.pop('reg_no')
        v['imageUrl'] = v.pop('image_url')
        v['documentUrl'] = v.pop('document_url', None)
        v['rejectionReason'] = v.pop('rejection_reason', None)
        v['price'] = float(v['price']) if v.get('price') is not None else 0.0
        return jsonify(v), 200
    return jsonify({'error': 'Vehicle not found.'}), 404

@app.route('/api/vehicles', methods=['POST'])
@token_required
@role_required(['owner', 'admin'])
def add_vehicle(current_user):
    data = request.get_json() or {}
    vid = str(uuid.uuid4())
    owner_id = current_user['id'] if current_user['role'] != 'admin' else (data.get('ownerId') or current_user['id'])

    # Validate price
    try:
        price = float(data.get('price', 0))
        if price <= 0:
            return jsonify({'error': 'Price must be greater than zero.'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid price value.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO vehicles (id, owner_id, brand, model, type, year, fuel_type, transmission, seats, reg_no, price, location, description, status, image_url, document_url) 
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (vid, owner_id, data.get('brand'), data.get('model'), data.get('type', 'Sedan'), data.get('year', 2023), 
         data.get('fuelType', 'Petrol'), data.get('transmission', 'Automatic'), data.get('seats', 5), data.get('regNo'), 
         price, data.get('location', 'Bangalore'), data.get('description'), 'Pending Approval', data.get('imageUrl'), data.get('documentUrl'))
    )
    
    # Notify admin about new vehicle submission
    cursor.execute(
        """INSERT INTO notifications (id, recipient_role, title, message, type)
           VALUES (%s, 'admin', %s, %s, 'vehicle_approval')""",
        (str(uuid.uuid4()), 'New Vehicle Listing Awaiting Approval', f"{data.get('brand')} {data.get('model')} listed by owner.")
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': vid, 'success': True}), 201

@app.route('/api/vehicles/<vid>', methods=['PUT'])
@token_required
def update_vehicle(current_user, vid):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM vehicles WHERE id = %s", (vid,))
    v = cursor.fetchone()
    if not v:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Vehicle not found.'}), 404

    is_admin = current_user['role'] == 'admin'
    is_owner = v['owner_id'] == current_user['id']

    if not is_admin and not is_owner:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Forbidden: You do not own this vehicle.'}), 403

    updates = []
    params = []
    field_map = {
        'brand': 'brand', 'model': 'model', 'type': 'type', 'year': 'year',
        'fuelType': 'fuel_type', 'transmission': 'transmission', 'seats': 'seats',
        'regNo': 'reg_no', 'price': 'price', 'location': 'location', 
        'description': 'description', 'imageUrl': 'image_url', 'documentUrl': 'document_url'
    }

    # Owner can update vehicle specs
    for k, db_col in field_map.items():
        if k in data:
            updates.append(f"{db_col} = %s")
            params.append(data[k])

    # Status updates
    if 'status' in data:
        new_status = data['status']
        if is_admin:
            # Admin can approve or reject
            if new_status in ['Available', 'Rejected', 'Maintenance', 'Inactive', 'Pending Approval']:
                updates.append("status = %s")
                params.append(new_status)
                if 'rejectionReason' in data:
                    updates.append("rejection_reason = %s")
                    params.append(data['rejectionReason'])
                    
                # Create notification for owner
                notif_type = 'vehicle_approved' if new_status == 'Available' else ('vehicle_rejected' if new_status == 'Rejected' else 'general')
                notif_title = f"Vehicle Listing {new_status}"
                notif_msg = f"Your vehicle {v['brand']} {v['model']} has been marked as {new_status}."
                if new_status == 'Rejected' and data.get('rejectionReason'):
                    notif_msg += f" Reason: {data['rejectionReason']}"
                    
                cursor.execute(
                    """INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
                       VALUES (%s, %s, 'owner', %s, %s, %s)""",
                    (str(uuid.uuid4()), v['owner_id'], notif_title, notif_msg, notif_type)
                )
        elif is_owner:
            # Owner can toggle Maintenance or reset to Pending Approval after editing
            if new_status in ['Maintenance', 'Available', 'Pending Approval']:
                # Cannot self-approve if currently Pending Approval or Rejected
                if new_status == 'Available' and v['status'] in ['Pending Approval', 'Rejected']:
                    pass # owner cannot self-approve
                else:
                    updates.append("status = %s")
                    params.append(new_status)

    if updates:
        params.append(vid)
        cursor.execute(f"UPDATE vehicles SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()

    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/vehicles/<vid>', methods=['DELETE'])
@token_required
def delete_vehicle(current_user, vid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT owner_id FROM vehicles WHERE id = %s", (vid,))
    v = cursor.fetchone()
    if not v:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Vehicle not found.'}), 404

    if current_user['role'] != 'admin' and v['owner_id'] != current_user['id']:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Forbidden: You do not own this vehicle.'}), 403

    cursor.execute("DELETE FROM vehicles WHERE id = %s", (vid,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/vehicles/upload-image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No file part provided.'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400
    if file:
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'url': f"/static/uploads/{filename}"}), 200

# ─────────────────────────────────────────────────────────────
# 4. BOOKINGS & DATE AVAILABILITY
# ─────────────────────────────────────────────────────────────

@app.route('/api/bookings/check-availability', methods=['POST'])
def check_availability():
    data = request.get_json() or {}
    vehicle_id = data.get('vehicleId')
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')

    if not vehicle_id or not start_date_str or not end_date_str:
        return jsonify({'available': False, 'reason': 'Missing parameters.'}), 400

    try:
        requested_start = datetime.datetime.strptime(start_date_str.split('T')[0], '%Y-%m-%d').date()
        requested_end = datetime.datetime.strptime(end_date_str.split('T')[0], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'available': False, 'reason': 'Invalid date format.'}), 400

    if requested_end < requested_start:
        return jsonify({'available': False, 'reason': 'End date must be on or after start date.'})

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check vehicle status
    cursor.execute("SELECT status FROM vehicles WHERE id = %s", (vehicle_id,))
    v = cursor.fetchone()
    if not v or v['status'] in ['Maintenance', 'Inactive', 'Rejected', 'Pending Approval']:
        cursor.close()
        conn.close()
        return jsonify({'available': False, 'reason': 'Vehicle is currently unavailable for booking.'})

    # Exact overlap formula: requestedStart <= existingEnd AND requestedEnd >= existingStart
    # Exclude Cancelled and Rejected bookings
    cursor.execute(
        """SELECT id, start_date, end_date, status FROM bookings 
           WHERE vehicle_id = %s 
             AND status IN ('Pending', 'Accepted', 'Confirmed', 'Active')
             AND (%s <= end_date AND %s >= start_date)""",
        (vehicle_id, requested_start, requested_end)
    )
    conflicting = cursor.fetchall()
    cursor.close()
    conn.close()

    if conflicting:
        return jsonify({'available': False, 'reason': 'Vehicle is already booked for the selected dates.'})

    return jsonify({'available': True})

@app.route('/api/bookings', methods=['POST'])
@token_required
def add_booking(current_user):
    data = request.get_json() or {}
    vehicle_id = data.get('vehicleId')
    user_id = current_user['id']
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')

    if not vehicle_id or not start_date_str or not end_date_str:
        return jsonify({'error': 'Missing required booking information.'}), 400

    try:
        requested_start = datetime.datetime.strptime(start_date_str.split('T')[0], '%Y-%m-%d').date()
        requested_end = datetime.datetime.strptime(end_date_str.split('T')[0], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400

    if requested_end < requested_start:
        return jsonify({'error': 'End date cannot be earlier than start date.'}), 400

    # User Age Check from MySQL
    dob = current_user.get('dob')
    if dob:
        today = datetime.date.today()
        if isinstance(dob, str):
            dob = datetime.datetime.strptime(dob, '%Y-%m-%d').date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            return jsonify({'error': 'Rental is only available for users aged 18 and above.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Atomic Transaction with Row Locking
        cursor.execute("SELECT id, owner_id, price, status FROM vehicles WHERE id = %s FOR UPDATE", (vehicle_id,))
        vehicle = cursor.fetchone()
        if not vehicle:
            conn.rollback()
            return jsonify({'error': 'Vehicle not found.'}), 404

        if vehicle['status'] != 'Available':
            conn.rollback()
            return jsonify({'error': 'Vehicle is not currently available for booking.'}), 400

        # Check for overlapping bookings
        cursor.execute(
            """SELECT id FROM bookings 
               WHERE vehicle_id = %s 
                 AND status IN ('Pending', 'Accepted', 'Confirmed', 'Active')
                 AND (%s <= end_date AND %s >= start_date)
               FOR UPDATE""",
            (vehicle_id, requested_start, requested_end)
        )
        if cursor.fetchone():
            conn.rollback()
            return jsonify({'error': 'Vehicle has already been booked for these dates.'}), 409

        # Calculate days & total
        price_per_day = float(vehicle['price'])
        days = (requested_end - requested_start).days + 1
        total_amount = float(data.get('totalAmount') or (days * price_per_day))

        bid = str(uuid.uuid4())
        cursor.execute(
            """INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status, license_number, license_expiry, aadhaar_last4)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (bid, vehicle_id, user_id, vehicle['owner_id'], requested_start, requested_end,
             'Pending', total_amount, price_per_day, days, 'Pending',
             data.get('licenseNumber'), data.get('licenseExpiry'), data.get('aadhaarLast4'))
        )

        # Notify Owner
        cursor.execute(
            """INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
               VALUES (%s, %s, 'owner', %s, %s, 'booking_request')""",
            (str(uuid.uuid4()), vehicle['owner_id'], 'New Booking Request', f"New booking received for {days} days from {current_user.get('name')}.")
        )

        conn.commit()
        return jsonify({'id': bid, 'success': True}), 201
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

@app.route('/api/bookings', methods=['GET'])
@token_required
def get_bookings(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = request.args.get('userId')
    owner_id = request.args.get('ownerId')
    
    query = "SELECT * FROM bookings WHERE 1=1"
    params = []

    # Enforce access control
    if current_user['role'] == 'admin':
        if user_id:
            query += " AND user_id = %s"
            params.append(user_id)
        if owner_id:
            query += " AND owner_id = %s"
            params.append(owner_id)
    elif current_user['role'] == 'owner':
        query += " AND owner_id = %s"
        params.append(current_user['id'])
    else: # 'user'
        query += " AND user_id = %s"
        params.append(current_user['id'])

    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    bookings = cursor.fetchall()

    for b in bookings:
        b['userId'] = b.pop('user_id')
        b['ownerId'] = b.pop('owner_id')
        b['vehicleId'] = b.pop('vehicle_id')
        b['startDate'] = b.pop('start_date').isoformat() if b.get('start_date') else None
        b['endDate'] = b.pop('end_date').isoformat() if b.get('end_date') else None
        b['totalAmount'] = float(b.pop('total_amount')) if b.get('total_amount') is not None else 0.0
        b['pricePerDay'] = float(b.pop('price_per_day')) if b.get('price_per_day') is not None else 0.0
        b['paymentStatus'] = b.pop('payment_status') or 'Pending'
        b['licenseNumber'] = b.pop('license_number', None)
        b['licenseExpiry'] = b.pop('license_expiry', None)
        b['aadhaarLast4'] = b.pop('aadhaar_last4', None)
        if 'created_at' in b and b['created_at']:
            b['createdAt'] = b.pop('created_at').isoformat()

    cursor.close()
    conn.close()
    return jsonify(bookings), 200

@app.route('/api/bookings/<bid>', methods=['GET'])
@token_required
def get_booking(current_user, bid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM bookings WHERE id = %s", (bid,))
    b = cursor.fetchone()
    cursor.close()
    conn.close()

    if not b:
        return jsonify({'error': 'Booking not found.'}), 404

    # Authorization
    if current_user['role'] != 'admin' and b['user_id'] != current_user['id'] and b['owner_id'] != current_user['id']:
        return jsonify({'error': 'Unauthorized access to this booking.'}), 403

    b['userId'] = b.pop('user_id')
    b['ownerId'] = b.pop('owner_id')
    b['vehicleId'] = b.pop('vehicle_id')
    b['startDate'] = b.pop('start_date').isoformat() if b.get('start_date') else None
    b['endDate'] = b.pop('end_date').isoformat() if b.get('end_date') else None
    b['totalAmount'] = float(b.pop('total_amount')) if b.get('total_amount') is not None else 0.0
    b['pricePerDay'] = float(b.pop('price_per_day')) if b.get('price_per_day') is not None else 0.0
    b['paymentStatus'] = b.pop('payment_status') or 'Pending'
    b['licenseNumber'] = b.pop('license_number', None)
    b['licenseExpiry'] = b.pop('license_expiry', None)
    b['aadhaarLast4'] = b.pop('aadhaar_last4', None)
    if 'created_at' in b and b['created_at']:
        b['createdAt'] = b.pop('created_at').isoformat()

    return jsonify(b), 200

@app.route('/api/bookings/<bid>', methods=['PUT'])
@token_required
def update_booking(current_user, bid):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM bookings WHERE id = %s", (bid,))
    b = cursor.fetchone()
    if not b:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Booking not found.'}), 404

    is_admin = current_user['role'] == 'admin'
    is_owner = b['owner_id'] == current_user['id']
    is_renter = b['user_id'] == current_user['id']

    if not is_admin and not is_owner and not is_renter:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Permission denied.'}), 403

    updates = []
    params = []

    if 'status' in data:
        new_status = data['status']
        # Owner can Accept or Reject
        if is_owner and new_status in ['Accepted', 'Rejected', 'Completed']:
            updates.append("status = %s")
            params.append(new_status)
        # Renter can Cancel if Pending or Accepted
        elif is_renter and new_status == 'Cancelled' and b['status'] in ['Pending', 'Accepted']:
            updates.append("status = %s")
            params.append(new_status)
        # Admin can set any status
        elif is_admin:
            updates.append("status = %s")
            params.append(new_status)

    if 'paymentStatus' in data and is_admin:
        updates.append("payment_status = %s")
        params.append(data['paymentStatus'])

    if updates:
        params.append(bid)
        cursor.execute(f"UPDATE bookings SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()

    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

# ─────────────────────────────────────────────────────────────
# 5. PAYMENTS & ADMIN VERIFICATION
# ─────────────────────────────────────────────────────────────

@app.route('/api/payments', methods=['GET'])
@token_required
def get_payments(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = request.args.get('userId')
    owner_id = request.args.get('ownerId')
    
    query = "SELECT * FROM payments WHERE 1=1"
    params = []

    if current_user['role'] == 'admin':
        if user_id:
            query += " AND user_id = %s"
            params.append(user_id)
        if owner_id:
            query += " AND owner_id = %s"
            params.append(owner_id)
    elif current_user['role'] == 'owner':
        query += " AND owner_id = %s"
        params.append(current_user['id'])
    else:
        query += " AND user_id = %s"
        params.append(current_user['id'])

    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    payments = cursor.fetchall()

    for p in payments:
        p['userId'] = p.pop('user_id')
        p['ownerId'] = p.pop('owner_id')
        p['bookingId'] = p.pop('booking_id')
        p['vehicleId'] = p.pop('vehicle_id', None)
        p['amount'] = float(p['amount']) if p.get('amount') is not None else 0.0
        p['method'] = p.get('method') or 'UPI'
        p['referenceNo'] = p.pop('reference_no', None)
        p['paymentProof'] = p.pop('payment_proof', None)
        p['adminNote'] = p.pop('admin_note', None)
        if 'created_at' in p and p['created_at']:
            p['paymentDate'] = p.pop('created_at').isoformat()

    cursor.close()
    conn.close()
    return jsonify(payments), 200

@app.route('/api/payments', methods=['POST'])
@token_required
def add_payment(current_user):
    data = request.get_json() or {}
    booking_id = data.get('bookingId')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM bookings WHERE id = %s", (booking_id,))
    booking = cursor.fetchone()

    if not booking:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Booking not found.'}), 404

    # Ensure booking belongs to caller
    if current_user['role'] != 'admin' and booking['user_id'] != current_user['id']:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Forbidden: You do not own this booking.'}), 403

    pid = str(uuid.uuid4())
    amount = float(data.get('amount') or booking['total_amount'])
    ref_no = data.get('referenceNo') or data.get('reference') or f"UPI-{uuid.uuid4().hex[:8].upper()}"

    cursor.execute(
        """INSERT INTO payments (id, booking_id, user_id, owner_id, vehicle_id, amount, status, method, reference_no, payment_proof)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (pid, booking_id, booking['user_id'], booking['owner_id'], booking['vehicle_id'],
         amount, 'Pending Verification', data.get('method', 'UPI'), ref_no, data.get('paymentProof'))
    )

    # Update booking payment status
    cursor.execute("UPDATE bookings SET payment_status = 'Pending Verification' WHERE id = %s", (booking_id,))

    # Notify admin for verification
    cursor.execute(
        """INSERT INTO notifications (id, recipient_role, title, message, type)
           VALUES (%s, 'admin', %s, %s, 'payment_verification')""",
        (str(uuid.uuid4()), 'Payment Verification Pending', f"Payment of ₹{amount:,.2f} for booking #{booking_id[:8]} requires admin verification.")
    )

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': pid, 'success': True}), 201

@app.route('/api/payments/<pid>', methods=['PUT'])
@token_required
@role_required(['admin'])
def update_payment(current_user, pid):
    data = request.get_json() or {}
    new_status = data.get('status')
    admin_note = data.get('adminNote')

    if new_status not in ['Paid', 'Rejected', 'Pending Verification']:
        return jsonify({'error': 'Invalid payment verification status.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM payments WHERE id = %s", (pid,))
    p = cursor.fetchone()
    if not p:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Payment record not found.'}), 404

    cursor.execute(
        "UPDATE payments SET status = %s, admin_note = %s WHERE id = %s",
        (new_status, admin_note, pid)
    )

    # Update associated booking
    booking_id = p['booking_id']
    if new_status == 'Paid':
        cursor.execute(
            "UPDATE bookings SET payment_status = 'Paid', status = 'Confirmed' WHERE id = %s",
            (booking_id,)
        )
        # Notify customer and owner
        cursor.execute(
            """INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
               VALUES (%s, %s, 'user', %s, %s, 'payment_confirmed')""",
            (str(uuid.uuid4()), p['user_id'], 'Payment Verified', f"Your payment of ₹{float(p['amount']):,.2f} has been verified. Booking is confirmed!")
        )
        cursor.execute(
            """INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
               VALUES (%s, %s, 'owner', %s, %s, 'booking_confirmed')""",
            (str(uuid.uuid4()), p['owner_id'], 'Booking Confirmed', f"Booking #{booking_id[:8]} payment verified by admin.")
        )
    elif new_status == 'Rejected':
        cursor.execute(
            "UPDATE bookings SET payment_status = 'Rejected' WHERE id = %s",
            (booking_id,)
        )
        cursor.execute(
            """INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
               VALUES (%s, %s, 'user', %s, %s, 'payment_rejected')""",
            (str(uuid.uuid4()), p['user_id'], 'Payment Rejected', f"Payment verification for booking #{booking_id[:8]} was rejected. {admin_note or ''}")
        )

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

# ─────────────────────────────────────────────────────────────
# 6. REVIEWS, FAVORITES, MAINTENANCE & NOTIFICATIONS
# ─────────────────────────────────────────────────────────────

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    vehicle_id = request.args.get('vehicleId')
    if vehicle_id:
        cursor.execute("SELECT * FROM reviews WHERE vehicle_id = %s ORDER BY created_at DESC", (vehicle_id,))
    else:
        cursor.execute("SELECT * FROM reviews ORDER BY created_at DESC")
    reviews = cursor.fetchall()
    for r in reviews:
        r['vehicleId'] = r.pop('vehicle_id')
        r['bookingId'] = r.pop('booking_id')
        r['userId'] = r.pop('user_id', None)
        r['reviewText'] = r.pop('review_text')
        if 'created_at' in r and r['created_at']:
            r['createdAt'] = r.pop('created_at').isoformat()
    cursor.close()
    conn.close()
    return jsonify(reviews), 200

@app.route('/api/reviews', methods=['POST'])
@token_required
def add_review(current_user):
    data = request.get_json() or {}
    rid = str(uuid.uuid4())
    rating = int(data.get('rating', 5))
    rating = max(1, min(5, rating))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reviews (id, vehicle_id, booking_id, user_id, rating, review_text) VALUES (%s, %s, %s, %s, %s, %s)",
        (rid, data['vehicleId'], data['bookingId'], current_user['id'], rating, data.get('text') or data.get('reviewText'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': rid, 'success': True}), 201

@app.route('/api/favorites', methods=['GET'])
@token_required
def get_favorites(current_user):
    user_id = current_user['id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT vehicle_id FROM favorites WHERE user_id = %s", (user_id,))
    favs = [row['vehicle_id'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(favs), 200

@app.route('/api/favorites', methods=['POST'])
@token_required
def add_favorite(current_user):
    data = request.get_json() or {}
    vehicle_id = data.get('vehicleId')
    user_id = current_user['id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT IGNORE INTO favorites (user_id, vehicle_id) VALUES (%s, %s)", (user_id, vehicle_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 201

@app.route('/api/favorites', methods=['DELETE'])
@token_required
def remove_favorite(current_user):
    vehicle_id = request.args.get('vehicleId') or (request.get_json() or {}).get('vehicleId')
    user_id = current_user['id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE user_id = %s AND vehicle_id = %s", (user_id, vehicle_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/maintenance', methods=['GET'])
@token_required
def get_maintenance(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    owner_id = request.args.get('ownerId')

    if current_user['role'] == 'admin':
        if owner_id:
            cursor.execute("SELECT * FROM maintenance WHERE owner_id = %s ORDER BY created_at DESC", (owner_id,))
        else:
            cursor.execute("SELECT * FROM maintenance ORDER BY created_at DESC")
    else:
        cursor.execute("SELECT * FROM maintenance WHERE owner_id = %s ORDER BY created_at DESC", (current_user['id'],))

    maint = cursor.fetchall()
    for m in maint:
        m['ownerId'] = m.pop('owner_id')
        m['vehicleId'] = m.pop('vehicle_id')
        m['cost'] = float(m['cost']) if m.get('cost') is not None else 0.0
        m['date'] = m.pop('date').isoformat() if m.get('date') else None
        if 'created_at' in m and m['created_at']:
            m['createdAt'] = m.pop('created_at').isoformat()

    cursor.close()
    conn.close()
    return jsonify(maint), 200

@app.route('/api/maintenance', methods=['POST'])
@token_required
@role_required(['owner', 'admin'])
def add_maintenance(current_user):
    data = request.get_json() or {}
    mid = str(uuid.uuid4())
    owner_id = current_user['id'] if current_user['role'] != 'admin' else (data.get('ownerId') or current_user['id'])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO maintenance (id, vehicle_id, owner_id, description, cost, status, date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (mid, data['vehicleId'], owner_id, data.get('description'), data.get('cost', 0), data.get('status', 'Pending'), data.get('date'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': mid, 'success': True}), 201

@app.route('/api/maintenance/<mid>', methods=['PUT'])
@token_required
def update_maintenance(current_user, mid):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT owner_id FROM maintenance WHERE id = %s", (mid,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Maintenance record not found.'}), 404

    if current_user['role'] != 'admin' and row['owner_id'] != current_user['id']:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Permission denied.'}), 403

    updates = []
    params = []
    for k, db_k in [('description', 'description'), ('cost', 'cost'), ('status', 'status'), ('date', 'date')]:
        if k in data:
            updates.append(f"{db_k} = %s")
            params.append(data[k])
    if updates:
        params.append(mid)
        cursor.execute(f"UPDATE maintenance SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()

    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    recipient_role = request.args.get('recipientRole')
    recipient_id = request.args.get('recipientId')

    if recipient_role:
        cursor.execute("SELECT * FROM notifications WHERE recipient_role = %s ORDER BY created_at DESC", (recipient_role,))
    elif recipient_id:
        cursor.execute("SELECT * FROM notifications WHERE recipient_id = %s ORDER BY created_at DESC", (recipient_id,))
    else:
        cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC")
    notifs = cursor.fetchall()
    for n in notifs:
        n['recipientRole'] = n.pop('recipient_role')
        n['recipientId'] = n.pop('recipient_id')
        if 'created_at' in n and n['created_at']:
            n['createdAt'] = n.pop('created_at').isoformat()

    cursor.close()
    conn.close()
    return jsonify(notifs), 200

@app.route('/api/notifications', methods=['POST'])
def add_notification():
    data = request.get_json() or {}
    nid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type) VALUES (%s, %s, %s, %s, %s, %s)",
        (nid, data.get('recipientId'), data.get('recipientRole'), data.get('title'), data.get('message'), data.get('type'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': nid}), 201

@app.route('/api/notifications/<nid>', methods=['PUT'])
def update_notification(nid):
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'status' in data:
        cursor.execute("UPDATE notifications SET status = %s WHERE id = %s", (data['status'], nid))
        conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
