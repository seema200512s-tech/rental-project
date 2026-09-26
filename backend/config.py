import os 
 
class Config: 
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'super-secret-rentride-key' 
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost' 
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root' 
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'rentride' 
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads') 
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024