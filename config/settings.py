import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "organisations",
    "venues",
    "seating",
    "ticketing",
    "orders",
    "payments",
    "attendees",
    "finance",
    "notifications",
    "blockchain",
    "audit",
    "core",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_SSL_REQUIRE = os.getenv("DATABASE_SSL_REQUIRE", "false").lower() == "true"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.getenv("DATABASE_CONN_MAX_AGE", "60")),
        ssl_require=DATABASE_SSL_REQUIRE,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
AUTH_USER_MODEL = "accounts.User"
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Maseru"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_OBJECT_STORAGE = os.getenv("USE_OBJECT_STORAGE", "false").lower() == "true"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
if USE_OBJECT_STORAGE:
    object_storage_bucket = os.getenv("OBJECT_STORAGE_BUCKET", "").strip()
    object_storage_access_key = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "").strip()
    object_storage_secret_key = os.getenv("OBJECT_STORAGE_SECRET_KEY", "").strip()
    missing_object_storage = [
        name
        for name, value in {
            "OBJECT_STORAGE_BUCKET": object_storage_bucket,
            "OBJECT_STORAGE_ACCESS_KEY": object_storage_access_key,
            "OBJECT_STORAGE_SECRET_KEY": object_storage_secret_key,
        }.items()
        if not value
    ]
    if missing_object_storage:
        raise ImproperlyConfigured(
            "Object storage is enabled but missing: " + ", ".join(missing_object_storage)
        )
    object_storage_options = {
        "bucket_name": object_storage_bucket,
        "access_key": object_storage_access_key,
        "secret_key": object_storage_secret_key,
        "endpoint_url": os.getenv("OBJECT_STORAGE_ENDPOINT_URL", "").strip() or None,
        "region_name": os.getenv("OBJECT_STORAGE_REGION", "").strip() or None,
        "file_overwrite": False,
        "querystring_auth": os.getenv("OBJECT_STORAGE_QUERYSTRING_AUTH", "true").lower() == "true",
    }
    custom_domain = os.getenv("OBJECT_STORAGE_CUSTOM_DOMAIN", "").strip()
    if custom_domain:
        object_storage_options["custom_domain"] = custom_domain
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": object_storage_options,
    }

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
SUPPORT_EMAIL = os.getenv("ETICKTING_SUPPORT_EMAIL", "support@etickting.local")
TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY", "")
TEXTBEE_DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID", "")
TEXTBEE_API_URL = os.getenv("TEXTBEE_API_URL", "https://api.textbee.dev/api/v1/gateway/send-sms")
OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_REQUESTS_PER_HOUR = int(os.getenv("OTP_REQUESTS_PER_HOUR", "5"))
REDIS_CONFIGURED = bool(os.getenv("REDIS_URL"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TICKETING_SIGNING_KEYS = os.getenv("TICKETING_SIGNING_KEYS", "")
TICKETING_VERIFY_KEYS = os.getenv("TICKETING_VERIFY_KEYS", "")
TICKETING_PUBLIC_VERIFY_RATE_LIMIT = int(os.getenv("TICKETING_PUBLIC_VERIFY_RATE_LIMIT", "30"))
TICKETING_SCAN_RATE_LIMIT = int(os.getenv("TICKETING_SCAN_RATE_LIMIT", "120"))
TICKETING_HOLD_MINUTES = int(os.getenv("TICKETING_HOLD_MINUTES", "10"))
TICKETING_CREDENTIAL_ENCRYPTION_KEY = os.getenv("TICKETING_CREDENTIAL_ENCRYPTION_KEY", "")
BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "")
BLOCKCHAIN_CONTRACT_ADDRESS = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", "")
BLOCKCHAIN_PRIVATE_KEY = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "")
CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache" if REDIS_CONFIGURED else "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": REDIS_URL if REDIS_CONFIGURED else "etickting-local-cache",
    }
}

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
