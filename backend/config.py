import os

# Safely load local .env if present
def _load_env_file():
    for base_dir in [os.path.dirname(os.path.abspath(__file__)), os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')]:
        env_file = os.path.join(base_dir, '.env')
        if os.path.isfile(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            os.environ.setdefault(k.strip(), v.strip())
            except Exception:
                pass
            break

_load_env_file()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'super-secret-rentride-key-2026'
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'Seema@123')
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'rentride'
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Razorpay Payment Gateway Credentials
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
    RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
