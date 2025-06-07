import os

VERSION = "1.0.0"
SECRET_KEY = os.getenv("SECRET_KEY")
JWT_ACCESS_EXPIRES_HOURS = int(os.getenv("JWT_ACCESS_EXPIRES_HOURS", "24"))
DEBUG = os.getenv("DEBUG", "False").lower() in ["true", "1"]
ALLOWED_API_KEYS = [key.strip() for key in os.getenv("ALLOWED_API_KEYS", "").split(",") if key.strip()]
required_env_vars = ["SECRET_KEY", "DB_PATH"]

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024