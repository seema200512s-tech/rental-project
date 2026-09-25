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
CORS(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def get_db_connection():
    return mysql.connector.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB']
    )

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    return jsonify({'error': f'Server Error: {str(e)}'}), 500

@app.route('/')
def index():
    return jsonify({'message': 'RentRide API Server is running. Access /api/health for status.'})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok"})

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['uid']
        except Exception as e:
            return jsonify({'message': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- AUTH ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    uid = str(uuid.uuid4())
    hashed_password = generate_password_hash(data['password'], method='pbkdf2:sha256')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash, phone, dob, address, role) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (uid, data['name'], data['email'], hashed_password, data.get('phone'), data.get('dob'), data.get('address'), data['role'])
        )
        conn.commit()
        return jsonify({'success': True, 'uid': uid}), 201
    except mysql.connector.IntegrityError:
        return jsonify({'error': 'Email already exists'}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (data['email'],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], data['password']):
        if not user['active']:
            return jsonify({'error': 'Account is suspended'}), 403
            
        token = jwt.encode({'uid': user['id'], 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1)}, app.config['SECRET_KEY'], algorithm="HS256")
        del user['password_hash']
        return jsonify({'token': token, 'user': user}), 200
    return jsonify({'error': 'Invalid credentials'}), 401

# --- USERS ---
@app.route('/api/users', methods=['GET'])
@token_required
def get_users(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    role = request.args.get('role')
    if role:
        cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users WHERE role = %s", (role,))
    else:
        cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users), 200

@app.route('/api/users/<uid>', methods=['GET'])
@token_required
def get_user(current_user, uid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, email, phone, dob, address, role, active, created_at FROM users WHERE id = %s", (uid,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user: return jsonify(user), 200
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/users/<uid>', methods=['PUT'])
@token_required
def update_user(current_user, uid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    for k in ['name', 'phone', 'address', 'active']:
        if k in data:
            updates.append(f"{k} = %s")
            params.append(data[k])
    if updates:
        params.append(uid)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

# --- VEHICLES ---
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
        
    cursor.execute(query, tuple(params))
    vehicles = cursor.fetchall()
    for v in vehicles:
        v['ownerId'] = v.pop('owner_id')
        v['fuelType'] = v.pop('fuel_type')
        v['regNo'] = v.pop('reg_no')
        v['imageUrl'] = v.pop('image_url')
        v['documentUrl'] = v.pop('document_url', None)
    cursor.close()
    conn.close()
    return jsonify(vehicles), 200

@app.route('/api/vehicles', methods=['POST'])
@token_required
def add_vehicle(current_user):
    data = request.get_json()
    vid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO vehicles (id, owner_id, brand, model, type, year, fuel_type, transmission, seats, reg_no, price, location, description, status, image_url, document_url) 
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (vid, data.get('ownerId'), data.get('brand'), data.get('model'), data.get('type'), data.get('year'), 
         data.get('fuelType'), data.get('transmission'), data.get('seats'), data.get('regNo'), 
         data.get('price'), data.get('location'), data.get('description'), data.get('status', 'Pending Approval'), data.get('imageUrl'), data.get('documentUrl'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': vid}), 201

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
        return jsonify(v), 200
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/vehicles/<vid>', methods=['PUT'])
@token_required
def update_vehicle(current_user, vid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    field_map = {
        'brand': 'brand', 'model': 'model', 'type': 'type', 'year': 'year',
        'fuelType': 'fuel_type', 'transmission': 'transmission', 'seats': 'seats',
        'regNo': 'reg_no', 'price': 'price', 'location': 'location', 
        'description': 'description', 'status': 'status', 'imageUrl': 'image_url',
        'documentUrl': 'document_url'
    }
    for k, v in data.items():
        if k in field_map:
            updates.append(f"{field_map[k]} = %s")
            params.append(v)
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
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vehicles WHERE id = %s", (vid,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/vehicles/upload-image', methods=['POST'])
def upload_image():
    # In fetchAPI we don't set Content-Type so it's multipart/form-data
    if 'image' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['image']
    if file.filename == '': return jsonify({'error': 'No file'}), 400
    if file:
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'url': f"/static/uploads/{filename}"}), 200

# --- BOOKINGS ---
@app.route('/api/bookings', methods=['GET'])
@token_required
def get_bookings(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = request.args.get('userId')
    owner_id = request.args.get('ownerId')
    query = "SELECT * FROM bookings WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    if owner_id:
        query += " AND owner_id = %s"
        params.append(owner_id)
        
    cursor.execute(query, tuple(params))
    bookings = cursor.fetchall()
    for b in bookings:
        b['userId'] = b.pop('user_id')
        b['ownerId'] = b.pop('owner_id')
        b['vehicleId'] = b.pop('vehicle_id')
        b['startDate'] = b.pop('start_date').isoformat() if b.get('start_date') else None
        b['endDate'] = b.pop('end_date').isoformat() if b.get('end_date') else None
        b['totalAmount'] = float(b.pop('total_amount')) if b.get('total_amount') else 0
        b['pricePerDay'] = float(b.pop('price_per_day')) if b.get('price_per_day') else 0
        b['days'] = b.get('days') or 0
        b['paymentStatus'] = b.pop('payment_status') if b.get('payment_status') else 'Pending'
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
        return jsonify({'error': 'Not found'}), 404
    b['userId'] = b.pop('user_id')
    b['ownerId'] = b.pop('owner_id')
    b['vehicleId'] = b.pop('vehicle_id')
    b['startDate'] = b.pop('start_date').isoformat() if b.get('start_date') else None
    b['endDate'] = b.pop('end_date').isoformat() if b.get('end_date') else None
    b['totalAmount'] = float(b.pop('total_amount')) if b.get('total_amount') else 0
    b['pricePerDay'] = float(b.pop('price_per_day')) if b.get('price_per_day') else 0
    b['days'] = b.get('days') or 0
    b['paymentStatus'] = b.pop('payment_status') if b.get('payment_status') else 'Pending'
    if 'created_at' in b and b['created_at']:
        b['createdAt'] = b.pop('created_at').isoformat()
    return jsonify(b), 200

@app.route('/api/bookings', methods=['POST'])
@token_required
def add_booking(current_user):
    data = request.get_json()
    bid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO bookings (id, vehicle_id, user_id, owner_id, start_date, end_date, status, total_amount, price_per_day, days, payment_status) 
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (bid, data['vehicleId'], data['userId'], data['ownerId'], data['startDate'], data['endDate'],
         data.get('status', 'Pending'), data['totalAmount'],
         data.get('pricePerDay', 0), data.get('days', 0), data.get('paymentStatus', 'Pending'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': bid}), 201

@app.route('/api/bookings/<bid>', methods=['PUT'])
@token_required
def update_booking(current_user, bid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if 'status' in data:
        updates.append("status = %s")
        params.append(data['status'])
    if 'paymentStatus' in data:
        updates.append("payment_status = %s")
        params.append(data['paymentStatus'])
    if updates:
        params.append(bid)
        cursor.execute(f"UPDATE bookings SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

@app.route('/api/bookings/check-availability', methods=['POST'])
def check_availability():
    data = request.get_json()
    vehicle_id = data.get('vehicleId')
    start_date_str = data.get('startDate')
    end_date_str = data.get('endDate')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT status FROM vehicles WHERE id = %s", (vehicle_id,))
    v = cursor.fetchone()
    if not v or v['status'] in ['Maintenance', 'Inactive', 'Rejected', 'Pending Approval']:
        cursor.close()
        conn.close()
        return jsonify({'available': False})
        
    cursor.execute("SELECT * FROM bookings WHERE vehicle_id = %s AND status IN ('Pending', 'Accepted', 'Confirmed', 'Active')", (vehicle_id,))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    
    requested_start = datetime.datetime.strptime(start_date_str.split('T')[0], '%Y-%m-%d').date()
    requested_end = datetime.datetime.strptime(end_date_str.split('T')[0], '%Y-%m-%d').date()
    if requested_end < requested_start: return jsonify({'available': False})
        
    for b in bookings:
        if requested_start <= b['end_date'] and requested_end >= b['start_date']:
            return jsonify({'available': False})
    return jsonify({'available': True})

# --- PAYMENTS ---
@app.route('/api/payments', methods=['GET'])
@token_required
def get_payments(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = request.args.get('userId')
    owner_id = request.args.get('ownerId')
    query = "SELECT * FROM payments WHERE 1=1"
    params = []
    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    if owner_id:
        query += " AND owner_id = %s"
        params.append(owner_id)
    cursor.execute(query, tuple(params))
    payments = cursor.fetchall()
    for p in payments:
        p['userId'] = p.pop('user_id')
        p['ownerId'] = p.pop('owner_id')
        p['bookingId'] = p.pop('booking_id')
        p['amount'] = float(p['amount'])
        p['method'] = p.get('method', 'UPI')
        if 'created_at' in p and p['created_at']:
            p['paymentDate'] = p.pop('created_at').isoformat()
    cursor.close()
    conn.close()
    return jsonify(payments), 200

@app.route('/api/payments', methods=['POST'])
@token_required
def add_payment(current_user):
    data = request.get_json()
    pid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (id, booking_id, user_id, owner_id, amount, status, method) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (pid, data['bookingId'], data['userId'], data['ownerId'], data['amount'],
         data.get('status', 'Pending Verification'), data.get('method', 'UPI'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': pid}), 201

@app.route('/api/payments/<pid>', methods=['PUT'])
@token_required
def update_payment(current_user, pid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'status' in data:
        cursor.execute("UPDATE payments SET status = %s WHERE id = %s", (data['status'], pid))
        conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

# --- REVIEWS ---
@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    vehicle_id = request.args.get('vehicleId')
    cursor.execute("SELECT * FROM reviews WHERE vehicle_id = %s", (vehicle_id,))
    reviews = cursor.fetchall()
    for r in reviews:
        r['vehicleId'] = r.pop('vehicle_id')
        r['bookingId'] = r.pop('booking_id')
        r['reviewText'] = r.pop('review_text')
    cursor.close()
    conn.close()
    return jsonify(reviews), 200

@app.route('/api/reviews', methods=['POST'])
@token_required
def add_review(current_user):
    data = request.get_json()
    rid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reviews (id, vehicle_id, booking_id, rating, review_text) VALUES (%s, %s, %s, %s, %s)",
        (rid, data['vehicleId'], data['bookingId'], data['rating'], data.get('text'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': rid}), 201

# --- FAVORITES ---
@app.route('/api/favorites', methods=['GET'])
@token_required
def get_favorites(current_user):
    user_id = request.args.get('userId')
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
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT IGNORE INTO favorites (user_id, vehicle_id) VALUES (%s, %s)", (data['userId'], data['vehicleId']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 201

@app.route('/api/favorites', methods=['DELETE'])
@token_required
def remove_favorite(current_user):
    user_id = request.args.get('userId')
    vehicle_id = request.args.get('vehicleId')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM favorites WHERE user_id = %s AND vehicle_id = %s", (user_id, vehicle_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

# --- MAINTENANCE ---
@app.route('/api/maintenance', methods=['GET'])
@token_required
def get_maintenance(current_user):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    owner_id = request.args.get('ownerId')
    if owner_id:
        cursor.execute("SELECT * FROM maintenance WHERE owner_id = %s", (owner_id,))
    else:
        cursor.execute("SELECT * FROM maintenance")
    maint = cursor.fetchall()
    for m in maint:
        m['ownerId'] = m.pop('owner_id')
        m['vehicleId'] = m.pop('vehicle_id')
        m['cost'] = float(m['cost']) if m.get('cost') else 0
        m['date'] = m.pop('date').isoformat() if m.get('date') else None
    cursor.close()
    conn.close()
    return jsonify(maint), 200

@app.route('/api/maintenance', methods=['POST'])
@token_required
def add_maintenance(current_user):
    data = request.get_json()
    mid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO maintenance (id, vehicle_id, owner_id, description, cost, status, date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (mid, data['vehicleId'], data['ownerId'], data.get('description'), data.get('cost'), data.get('status', 'Pending'), data.get('date'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': mid}), 201

@app.route('/api/maintenance/<mid>', methods=['PUT'])
@token_required
def update_maintenance(current_user, mid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
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

# --- NOTIFICATIONS ---
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    recipient_role = request.args.get('recipientRole')
    recipient_id = request.args.get('recipientId')
    if recipient_role:
        cursor.execute("SELECT * FROM notifications WHERE recipient_role = %s", (recipient_role,))
    elif recipient_id:
        cursor.execute("SELECT * FROM notifications WHERE recipient_id = %s", (recipient_id,))
    else:
        cursor.execute("SELECT * FROM notifications")
    notifs = cursor.fetchall()
    for n in notifs:
        n['recipientRole'] = n.pop('recipient_role')
        n['recipientId'] = n.pop('recipient_id')
    cursor.close()
    conn.close()
    return jsonify(notifs), 200

@app.route('/api/notifications', methods=['POST'])
def add_notification():
    data = request.get_json()
    nid = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notifications (id, recipient_id, recipient_role, title, message) VALUES (%s, %s, %s, %s, %s)",
        (nid, data.get('recipientId'), data.get('recipientRole'), data.get('title'), data.get('message'))
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'id': nid}), 201

@app.route('/api/notifications/<nid>', methods=['PUT'])
def update_notification(nid):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    if 'status' in data:
        cursor.execute("UPDATE notifications SET status = %s WHERE id = %s", (data['status'], nid))
        conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
