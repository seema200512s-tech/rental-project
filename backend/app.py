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
from werkzeug.exceptions import HTTPException
import jwt
import hmac
import hashlib

try:
    import razorpay
except ImportError:
    razorpay = None

try:
    from config import Config
except ImportError:
    from backend.config import Config

app = Flask(__name__)
app.config.from_object(Config)

def get_razorpay_client():
    key_id = (app.config.get('RAZORPAY_KEY_ID') or '').strip()
    key_secret = (app.config.get('RAZORPAY_KEY_SECRET') or '').strip()
    if not key_id or not key_secret or 'REPLACE' in key_id or 'REPLACE' in key_secret:
        return None
    if razorpay is None:
        return None
    try:
        return razorpay.Client(auth=(key_id, key_secret))
    except Exception as e:
        app.logger.error(f"Failed to initialize Razorpay client: {e}")
        return None


# Configure CORS dynamically to allow local development on any port and production Vercel origins
cors_origins_env = os.environ.get('CORS_ORIGINS', '')
allowed_origins = [
    r"^http://localhost(:\d+)?$",
    r"^http://127\.0\.0\.1(:\d+)?$",
    r"^https:\/\/.*\.vercel\.app$"
]
if cors_origins_env:
    for o in cors_origins_env.split(','):
        if o.strip() and o.strip() not in allowed_origins:
            allowed_origins.append(o.strip())

CORS(app, resources={
    r"/.*": {
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
    if isinstance(e, HTTPException):
        return jsonify({'error': e.description}), e.code
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
    # Admin, the user themselves, or an owner whose vehicle was booked by this user can view the profile
    is_authorized = current_user['role'] == 'admin' or current_user['id'] == uid
    if not is_authorized and current_user['role'] == 'owner':
        chk_conn = get_db_connection()
        chk_cur = chk_conn.cursor()
        chk_cur.execute("""
            SELECT 1 FROM bookings b 
            JOIN vehicles v ON b.vehicle_id = v.id 
            WHERE b.user_id = %s AND v.owner_id = %s LIMIT 1
        """, (uid, current_user['id']))
        if chk_cur.fetchone():
            is_authorized = True
        chk_cur.close()
        chk_conn.close()

    if not is_authorized:
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
    show_all = request.args.get('all') == 'true'
    
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
    elif show_all:
        # Admin or management view of all vehicles regardless of status
        pass
    else:
        # Check if caller passed an admin token in Authorization header
        is_admin = False
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                decoded = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
                if decoded.get('role') == 'admin':
                    is_admin = True
            except Exception:
                pass
        if not is_admin:
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
    # Support both JSON payload and multipart/form-data
    if request.is_json:
        data = request.get_json() or {}
        image_url = data.get('imageUrl')
        document_url = data.get('documentUrl')
    else:
        data = request.form.to_dict()
        image_url = data.get('imageUrl')
        document_url = data.get('documentUrl')
        
        # Handle uploaded image directly if sent via multipart
        if 'image' in request.files and request.files['image'].filename:
            img_file = request.files['image']
            img_fname = secure_filename(f"{uuid.uuid4()}_{img_file.filename}")
            img_file.save(os.path.join(app.config['UPLOAD_FOLDER'], img_fname))
            image_url = f"/static/uploads/{img_fname}"
            
        if 'document' in request.files and request.files['document'].filename:
            doc_file = request.files['document']
            doc_fname = secure_filename(f"{uuid.uuid4()}_{doc_file.filename}")
            doc_file.save(os.path.join(app.config['UPLOAD_FOLDER'], doc_fname))
            document_url = f"/static/uploads/{doc_fname}"

    brand = (data.get('brand') or '').strip()
    model = (data.get('model') or '').strip()
    v_type = (data.get('type') or 'Car').strip()
    reg_no = (data.get('regNo') or '').strip().upper()
    location = (data.get('location') or 'Bangalore').strip()
    description = (data.get('description') or '').strip()

    if not brand or not model:
        return jsonify({'error': 'Vehicle brand and model are required.'}), 400

    try:
        price = float(data.get('price', 0))
        if price <= 0:
            return jsonify({'error': 'Price must be greater than zero.'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid price value.'}), 400

    try:
        year = int(data.get('year', datetime.date.today().year))
    except (ValueError, TypeError):
        year = datetime.date.today().year

    try:
        seats = int(data.get('seats', 5))
    except (ValueError, TypeError):
        seats = 5

    vid = str(uuid.uuid4())
    owner_id = current_user['id'] if current_user['role'] != 'admin' else (data.get('ownerId') or current_user['id'])

    cursor = None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO vehicles (id, owner_id, brand, model, type, year, fuel_type, transmission, seats, reg_no, price, location, description, status, image_url, document_url) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (vid, owner_id, brand, model, v_type, year, 
             data.get('fuelType', 'Petrol'), data.get('transmission', 'Automatic'), seats, reg_no, 
             price, location, description, 'Pending Approval', image_url, document_url)
        )
        
        # Notify admin about new vehicle submission
        cursor.execute(
            """INSERT INTO notifications (id, recipient_role, title, message, type)
               VALUES (%s, 'admin', %s, %s, 'vehicle_approval')""",
            (str(uuid.uuid4()), 'New Vehicle Listing Awaiting Approval', f"{brand} {model} listed by owner.")
        )
        
        conn.commit()
        return jsonify({'id': vid, 'success': True, 'message': 'Vehicle submitted successfully for admin approval.'}), 201
    except mysql.connector.Error as err:
        app.logger.error(f"Database error in add_vehicle: {str(err)}")
        return jsonify({'error': f'Database error: {str(err)}'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
    file = None
    for key in ['image', 'document', 'file']:
        if key in request.files:
            file = request.files[key]
            break
    if not file and len(request.files) > 0:
        file = next(iter(request.files.values()))

    if not file or file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400

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
        p['razorpayOrderId'] = p.pop('razorpay_order_id', None)
        p['razorpayPaymentId'] = p.pop('razorpay_payment_id', None)
        p['razorpaySignature'] = p.pop('razorpay_signature', None)
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

# ─────────────────────────────────────────────────────────────
# RAZORPAY UPI PAYMENT GATEWAY & VERIFICATION
# ─────────────────────────────────────────────────────────────

@app.route('/api/payments/create-order', methods=['POST'])
@token_required
def create_payment_order(current_user):
    data = request.get_json() or {}
    booking_id = data.get('bookingId')

    if not booking_id:
        return jsonify({'error': 'Missing booking ID.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT b.*, v.brand, v.model, v.status AS vehicle_status
        FROM bookings b
        JOIN vehicles v ON b.vehicle_id = v.id
        WHERE b.id = %s
    """, (booking_id,))
    booking = cursor.fetchone()

    if not booking:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Booking not found.'}), 404

    # Ensure booking belongs to caller or caller is admin
    if current_user['role'] != 'admin' and booking['user_id'] != current_user['id']:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Forbidden: You do not own this booking.'}), 403

    # Check booking status
    if booking['status'] in ['Cancelled', 'Rejected']:
        cursor.close()
        conn.close()
        return jsonify({'error': f"Cannot pay for a {booking['status'].lower()} booking."}), 400

    if booking['payment_status'] == 'Paid' or booking['status'] == 'Confirmed':
        cursor.close()
        conn.close()
        return jsonify({'error': 'This booking has already been paid and confirmed.'}), 400

    # Availability re-check for vehicle status
    if booking['vehicle_status'] in ['Maintenance', 'Inactive', 'Rejected', 'Pending Approval']:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Vehicle is currently unavailable for rental.'}), 400

    # Prevent overlapping confirmed bookings
    cursor.execute("""
        SELECT id FROM bookings
        WHERE vehicle_id = %s
          AND status IN ('Confirmed', 'Active')
          AND id != %s
          AND (%s <= end_date AND %s >= start_date)
    """, (booking['vehicle_id'], booking_id, booking['start_date'], booking['end_date']))
    overlap = cursor.fetchone()
    if overlap:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Vehicle is already booked by another confirmed reservation for these dates.'}), 409

    # Total amount from MySQL - Never trust frontend amount!
    amount_rupees = float(booking['total_amount'])
    if amount_rupees <= 0:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Invalid booking amount.'}), 400

    amount_paise = int(round(amount_rupees * 100))

    client = get_razorpay_client()
    if not client:
        cursor.close()
        conn.close()
        return jsonify({
            'error': 'Razorpay gateway is not configured. Please add valid RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to your backend environment.'
        }), 503

    try:
        # Check if an existing order was already created for this booking
        existing_order_id = booking.get('razorpay_order_id')
        rzp_order = None
        if existing_order_id:
            try:
                fetched = client.order.fetch(existing_order_id)
                if fetched and fetched.get('amount') == amount_paise and fetched.get('status') in ['created', 'attempted']:
                    rzp_order = fetched
            except Exception:
                rzp_order = None

        if not rzp_order:
            order_receipt = f"b_{booking_id.replace('-', '')[:30]}"
            order_payload = {
                'amount': amount_paise,
                'currency': 'INR',
                'receipt': order_receipt,
                'notes': {
                    'booking_id': booking_id,
                    'user_id': current_user['id'],
                    'vehicle_id': booking['vehicle_id'],
                    'vehicle_name': f"{booking['brand']} {booking['model']}"
                }
            }
            rzp_order = client.order.create(data=order_payload)
            cursor.execute("UPDATE bookings SET razorpay_order_id = %s WHERE id = %s", (rzp_order['id'], booking_id))
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            'orderId': rzp_order['id'],
            'amount': amount_paise,
            'amountInRupees': amount_rupees,
            'currency': 'INR',
            'keyId': app.config.get('RAZORPAY_KEY_ID', ''),
            'bookingId': booking_id,
            'vehicleName': f"{booking['brand']} {booking['model']}",
            'prefill': {
                'name': current_user.get('name') or '',
                'email': current_user.get('email') or '',
                'contact': current_user.get('phone') or ''
            }
        }), 200

    except Exception as e:
        cursor.close()
        conn.close()
        app.logger.error(f"Razorpay create-order error: {str(e)}")
        return jsonify({'error': f"Failed to initialize payment gateway order: {str(e)}"}), 500


@app.route('/api/payments/verify', methods=['POST'])
@token_required
def verify_payment(current_user):
    data = request.get_json() or {}
    booking_id = data.get('bookingId')
    rzp_order_id = data.get('razorpay_order_id')
    rzp_payment_id = data.get('razorpay_payment_id')
    rzp_signature = data.get('razorpay_signature')

    if not booking_id or not rzp_order_id or not rzp_payment_id or not rzp_signature:
        return jsonify({'error': 'Missing required payment verification parameters.'}), 400

    client = get_razorpay_client()
    if not client:
        return jsonify({'error': 'Razorpay gateway is not configured on the server.'}), 503

    # 1. Official Signature Verification
    try:
        params_dict = {
            'razorpay_order_id': rzp_order_id,
            'razorpay_payment_id': rzp_payment_id,
            'razorpay_signature': rzp_signature
        }
        client.utility.verify_payment_signature(params_dict)
    except Exception as e:
        app.logger.warning(f"Signature verification failed for order {rzp_order_id}: {str(e)}")
        return jsonify({'error': 'Invalid payment signature. Verification failed.'}), 400

    # 2. Fetch payment details from Razorpay to validate status, amount, currency, order_id
    try:
        payment_details = client.payment.fetch(rzp_payment_id)
        if not payment_details:
            return jsonify({'error': 'Unable to retrieve payment details from gateway.'}), 400

        payment_status = payment_details.get('status')
        if payment_status not in ['captured', 'authorized']:
            return jsonify({
                'error': f"Payment is not confirmed. Current status: {payment_status}."
            }), 400

        if payment_details.get('order_id') != rzp_order_id:
            return jsonify({'error': 'Order ID mismatch between signature and gateway record.'}), 400

        if payment_details.get('currency') != 'INR':
            return jsonify({'error': 'Invalid payment currency.'}), 400
    except Exception as e:
        app.logger.error(f"Error fetching payment details from Razorpay: {str(e)}")
        return jsonify({'error': f"Gateway error during payment verification: {str(e)}"}), 500

    # 3. Database transaction with row lock & idempotency check
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # A. Idempotency Check: Has this payment ID already been recorded as Paid?
        cursor.execute("SELECT * FROM payments WHERE razorpay_payment_id = %s", (rzp_payment_id,))
        existing_pmt = cursor.fetchone()
        if existing_pmt and existing_pmt.get('status') == 'Paid':
            cursor.execute("""
                SELECT b.*, v.brand, v.model
                FROM bookings b
                JOIN vehicles v ON b.vehicle_id = v.id
                WHERE b.id = %s
            """, (existing_pmt['booking_id'],))
            b_info = cursor.fetchone()
            conn.commit()
            return jsonify({
                'success': True,
                'alreadyProcessed': True,
                'paymentId': rzp_payment_id,
                'orderId': rzp_order_id,
                'bookingId': existing_pmt['booking_id'],
                'amount': float(existing_pmt['amount']),
                'vehicleName': f"{b_info['brand']} {b_info['model']}" if b_info else "Vehicle",
                'startDate': str(b_info['start_date']) if b_info else "",
                'endDate': str(b_info['end_date']) if b_info else "",
                'paymentDate': existing_pmt['created_at'].strftime("%d %b %Y, %I:%M %p") if existing_pmt.get('created_at') else datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
                'status': 'Confirmed',
                'message': 'Payment already verified and booking confirmed.'
            }), 200

        # B. Lock the booking row
        cursor.execute("""
            SELECT b.*, v.brand, v.model, v.status AS vehicle_status
            FROM bookings b
            JOIN vehicles v ON b.vehicle_id = v.id
            WHERE b.id = %s
            FOR UPDATE
        """, (booking_id,))
        booking = cursor.fetchone()

        if not booking:
            conn.rollback()
            return jsonify({'error': 'Booking not found.'}), 404

        if current_user['role'] != 'admin' and booking['user_id'] != current_user['id']:
            conn.rollback()
            return jsonify({'error': 'Forbidden: You do not own this booking.'}), 403

        # Validate amount
        expected_amount_paise = int(round(float(booking['total_amount']) * 100))
        paid_amount_paise = int(payment_details.get('amount', 0))
        if paid_amount_paise != expected_amount_paise:
            conn.rollback()
            return jsonify({
                'error': f"Paid amount (₹{paid_amount_paise/100:.2f}) does not match booking total (₹{expected_amount_paise/100:.2f})."
            }), 400

        # C. Recheck vehicle availability & prevent overlapping confirmed bookings
        cursor.execute("""
            SELECT id FROM bookings
            WHERE vehicle_id = %s
              AND status IN ('Confirmed', 'Active')
              AND id != %s
              AND (%s <= end_date AND %s >= start_date)
            FOR UPDATE
        """, (booking['vehicle_id'], booking_id, booking['start_date'], booking['end_date']))
        conflict = cursor.fetchone()
        if conflict:
            conn.rollback()
            return jsonify({
                'error': 'Vehicle is already booked by another confirmed reservation for these dates. Payment requires manual resolution or refund.'
            }), 409

        # D. Record Payment in payments table
        payment_uuid = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO payments (
                id, booking_id, user_id, owner_id, vehicle_id,
                amount, status, method, reference_no,
                razorpay_order_id, razorpay_payment_id, razorpay_signature
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            payment_uuid,
            booking_id,
            booking['user_id'],
            booking['owner_id'],
            booking['vehicle_id'],
            float(booking['total_amount']),
            'Paid',
            'UPI_RAZORPAY',
            rzp_payment_id,
            rzp_order_id,
            rzp_payment_id,
            rzp_signature
        ))

        # E. Update Booking to Confirmed & Paid
        cursor.execute("""
            UPDATE bookings
            SET status = 'Confirmed',
                payment_status = 'Paid',
                razorpay_order_id = %s
            WHERE id = %s
        """, (rzp_order_id, booking_id))

        # F. Notifications
        amount_fmt = f"{float(booking['total_amount']):,.2f}"
        cursor.execute("""
            INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
            VALUES (%s, %s, 'user', %s, %s, 'payment_success')
        """, (
            str(uuid.uuid4()),
            booking['user_id'],
            'Payment Successful',
            f"Your payment of ₹{amount_fmt} for booking #{booking_id[:8]} ({booking['brand']} {booking['model']}) was verified. Booking is Confirmed!"
        ))
        cursor.execute("""
            INSERT INTO notifications (id, recipient_id, recipient_role, title, message, type)
            VALUES (%s, %s, 'owner', %s, %s, 'booking_confirmed')
        """, (
            str(uuid.uuid4()),
            booking['owner_id'],
            'Booking Confirmed',
            f"Booking #{booking_id[:8]} for {booking['brand']} {booking['model']} has been paid (₹{amount_fmt}) and confirmed."
        ))
        cursor.execute("""
            INSERT INTO notifications (id, recipient_role, title, message, type)
            VALUES (%s, 'admin', %s, %s, 'payment_success')
        """, (
            str(uuid.uuid4()),
            'Payment Verified (Razorpay)',
            f"Payment of ₹{amount_fmt} verified for booking #{booking_id[:8]} (Payment ID: {rzp_payment_id})."
        ))

        conn.commit()

        return jsonify({
            'success': True,
            'paymentId': rzp_payment_id,
            'orderId': rzp_order_id,
            'bookingId': booking_id,
            'amount': float(booking['total_amount']),
            'vehicleName': f"{booking['brand']} {booking['model']}",
            'startDate': str(booking['start_date']),
            'endDate': str(booking['end_date']),
            'paymentDate': datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
            'status': 'Confirmed',
            'message': 'Payment verified and booking confirmed successfully!'
        }), 200

    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error in verify_payment transaction: {str(e)}")
        return jsonify({'error': f"Failed to confirm booking: {str(e)}"}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/payments/webhook', methods=['POST'])
def razorpay_webhook():
    webhook_secret = (app.config.get('RAZORPAY_WEBHOOK_SECRET') or '').strip()
    if not webhook_secret or 'REPLACE' in webhook_secret:
        return jsonify({'error': 'Webhook secret not configured on server'}), 500

    client = get_razorpay_client()
    if not client:
        return jsonify({'error': 'Razorpay client not configured'}), 500

    webhook_signature = request.headers.get('X-Razorpay-Signature')
    if not webhook_signature:
        return jsonify({'error': 'Missing X-Razorpay-Signature header'}), 400

    raw_body = request.get_data(as_text=True)

    try:
        client.utility.verify_webhook_signature(raw_body, webhook_signature, webhook_secret)
    except Exception as e:
        app.logger.warning(f"Invalid webhook signature: {str(e)}")
        return jsonify({'error': 'Invalid webhook signature'}), 400

    event_payload = request.get_json() or {}
    event_type = event_payload.get('event')

    if event_type == 'payment.captured':
        payment_entity = event_payload.get('payload', {}).get('payment', {}).get('entity', {})
        rzp_payment_id = payment_entity.get('id')
        rzp_order_id = payment_entity.get('order_id')
        notes = payment_entity.get('notes', {})
        booking_id = notes.get('booking_id')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # Check idempotency
            cursor.execute("SELECT id, status FROM payments WHERE razorpay_payment_id = %s", (rzp_payment_id,))
            existing = cursor.fetchone()
            if existing and existing.get('status') == 'Paid':
                cursor.close()
                conn.close()
                return jsonify({'status': 'ok', 'message': 'Payment already processed'}), 200

            if not booking_id and rzp_order_id:
                cursor.execute("SELECT id FROM bookings WHERE razorpay_order_id = %s", (rzp_order_id,))
                found = cursor.fetchone()
                if found:
                    booking_id = found['id']

            if booking_id:
                cursor.execute("""
                    SELECT b.*, v.brand, v.model 
                    FROM bookings b 
                    JOIN vehicles v ON b.vehicle_id = v.id 
                    WHERE b.id = %s FOR UPDATE
                """, (booking_id,))
                b = cursor.fetchone()
                if b and b['payment_status'] != 'Paid':
                    pid = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO payments (
                            id, booking_id, user_id, owner_id, vehicle_id,
                            amount, status, method, reference_no,
                            razorpay_order_id, razorpay_payment_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'Paid', 'UPI_RAZORPAY', %s, %s, %s)
                    """, (
                        pid, booking_id, b['user_id'], b['owner_id'], b['vehicle_id'],
                        float(b['total_amount']), rzp_payment_id, rzp_order_id, rzp_payment_id
                    ))
                    cursor.execute("""
                        UPDATE bookings 
                        SET status = 'Confirmed', payment_status = 'Paid', razorpay_order_id = %s 
                        WHERE id = %s
                    """, (rzp_order_id, booking_id))
                    conn.commit()
        except Exception as e:
            conn.rollback()
            app.logger.error(f"Error processing webhook: {str(e)}")
        finally:
            cursor.close()
            conn.close()

    elif event_type == 'payment.failed':
        payment_entity = event_payload.get('payload', {}).get('payment', {}).get('entity', {})
        rzp_payment_id = payment_entity.get('id')
        rzp_order_id = payment_entity.get('order_id')
        notes = payment_entity.get('notes', {})
        booking_id = notes.get('booking_id')
        if booking_id:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT user_id, owner_id, vehicle_id, total_amount FROM bookings WHERE id = %s", (booking_id,))
                b = cursor.fetchone()
                if b:
                    pid = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO payments (
                            id, booking_id, user_id, owner_id, vehicle_id,
                            amount, status, method, reference_no,
                            razorpay_order_id, razorpay_payment_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'Failed', 'UPI_RAZORPAY', %s, %s, %s)
                    """, (
                        pid, booking_id, b['user_id'], b['owner_id'], b['vehicle_id'],
                        float(b['total_amount']), rzp_payment_id, rzp_order_id, rzp_payment_id
                    ))
                    conn.commit()
            except Exception as e:
                conn.rollback()
                app.logger.error(f"Error recording failed payment webhook: {str(e)}")
            finally:
                cursor.close()
                conn.close()

    return jsonify({'status': 'ok'}), 200


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
