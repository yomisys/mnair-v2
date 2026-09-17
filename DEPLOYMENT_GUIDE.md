# MNAIR Platform - Deployment Guide

## Overview

This guide covers deploying the complete Make Nigeria AI Ready (MNAIR) platform to production.

## Project Status

- **Completion**: 12/13 modules (92%)
- **Status**: Production Ready ✅
- **Backend**: Complete with security hardening
- **Frontend**: Complete with admin dashboard and public pages
- **Remaining**: Module 6B (optional advanced admin features)

## Architecture

### Backend (FastAPI + Python)
- **Framework**: FastAPI
- **Database**: PostgreSQL (async SQLAlchemy 2.0)
- **Cache**: Redis
- **Storage**: MinIO (S3-compatible)
- **Tasks**: Celery with Celery Beat
- **API Docs**: Auto-generated at `/docs` and `/redoc`

### Frontend (React + TypeScript)
- **Framework**: React 18 with TypeScript 5
- **Build Tool**: Vite 4
- **UI Library**: Material-UI 5
- **Routing**: React Router 6
- **HTTP Client**: Axios

## Prerequisites

### System Requirements
- **OS**: Ubuntu 20.04+ or similar Linux distribution
- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 20GB+ for application and database

### Software Requirements
- Docker & Docker Compose (recommended) OR:
  - Python 3.8+
  - Node.js 20+
  - PostgreSQL 14+
  - Redis 6+
  - MinIO or S3-compatible storage

## Deployment Options

### Option 1: Docker Compose (Recommended)

The platform includes Docker Compose configuration for easy deployment.

1. **Clone the repository**:
```bash
git clone <repository-url>
cd mnair
```

2. **Set up environment variables**:
```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env with production values

# Frontend
cp frontend/.env.example frontend/.env
# Edit frontend/.env with production API URL
```

3. **Start services**:
```bash
docker-compose up -d
```

Services will be available at:
- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5433
- Redis: localhost:6380
- MinIO: localhost:9000 (Console: localhost:9001)

### Option 2: Manual Deployment

#### Backend Deployment

1. **Install dependencies**:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Set up database**:
```bash
# Create PostgreSQL database
createdb mnair_production

# Run migrations (if using Alembic)
alembic upgrade head

# Initialize database
python init_db.py
```

3. **Load curriculum data**:
```bash
python -m app.curriculum.loader
```

4. **Start backend services**:

**API Server**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Celery Worker**:
```bash
celery -A app.tasks.celery_app worker --loglevel=info
```

**Celery Beat Scheduler**:
```bash
celery -A app.tasks.celery_app beat --loglevel=info
```

#### Frontend Deployment

1. **Install dependencies**:
```bash
cd frontend
npm install
```

2. **Build for production**:
```bash
npm run build
```

3. **Serve with Nginx**:
```nginx
server {
    listen 80;
    server_name mnair.gov.ng;

    root /var/www/mnair/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Environment Configuration

### Backend Environment Variables

Create `backend/.env`:

```env
# Application
APP_NAME="MNAIR Platform"
APP_ENV=production
APP_DEBUG=false
API_VERSION=v1
LOG_LEVEL=INFO

# Database
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=mnair_production
DATABASE_USER=mnair_user
DATABASE_PASSWORD=<strong-password>

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=<redis-password>

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# MinIO / S3
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_BUCKET=mnair-certificates
MINIO_SECURE=false  # Set to true with HTTPS

# JWT
JWT_SECRET_KEY=<generate-strong-secret>
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=10080  # 7 days

# CORS
CORS_ORIGINS=https://mnair.gov.ng,https://www.mnair.gov.ng

# API Keys
TERMII_API_KEY=<termii-api-key>
TERMII_SENDER_ID=MNAIR
AFRICAS_TALKING_USERNAME=<username>
AFRICAS_TALKING_API_KEY=<api-key>
AFRICAS_TALKING_SHORTCODE=*384*8080#
# Free learner channels (v2 — WhatsApp removed)
TELEGRAM_BOT_TOKEN=<from @BotFather>
TELEGRAM_BOT_USERNAME=<bot handle without @>
TELEGRAM_WEBHOOK_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(32))">
VAPID_PUBLIC_KEY=<from generate_vapid_keys()>
VAPID_PRIVATE_KEY=<from generate_vapid_keys()>
SMS_REMINDERS_ENABLED=false

# NDPA Compliance
DATA_RETENTION_DAYS=90
```

### Frontend Environment Variables

Create `frontend/.env`:

```env
VITE_API_URL=https://api.mnair.gov.ng
```

## Security Checklist

Before deploying to production:

- [ ] Change all default secrets and API keys
- [ ] Enable HTTPS with valid SSL certificates
- [ ] Update CORS origins to production domains only
- [ ] Set `APP_ENV=production` in backend
- [ ] Enable HSTS in production (automatic in code)
- [ ] Configure firewall rules (allow 80, 443, block others)
- [ ] Set up database backups (automated via Celery)
- [ ] Configure Redis authentication
- [ ] Secure MinIO with strong credentials
- [ ] Review and update rate limiting thresholds
- [ ] Enable PostgreSQL SSL connections
- [ ] Set up monitoring and alerting
- [ ] Configure log rotation
- [ ] Review NDPA compliance settings

## Database Initialization

1. **Create admin user** (in Python shell):
```python
from app.database import AsyncSessionLocal
from app.models.user import User
from app.utils.auth import get_password_hash
import asyncio

async def create_admin():
    async with AsyncSessionLocal() as db:
        admin = User(
            phone_number="+234XXXXXXXXXX",
            name="Admin User",
            role="admin",
            language="en",
            password_hash=get_password_hash("secure-password"),
            is_active=True,
            consent_given=True
        )
        db.add(admin)
        await db.commit()
        print("Admin user created")

asyncio.run(create_admin())
```

2. **Load curriculum**:
```bash
python -m app.curriculum.loader
```

## Monitoring & Maintenance

### Health Checks

- Backend: `GET /health`
- Database: Celery health_check task runs hourly
- Scheduled tasks: Check Celery Beat logs

### Automated Tasks

The platform runs several automated tasks:

| Task | Schedule | Purpose |
|------|----------|---------|
| Daily Analytics | 1 AM WAT | Calculate daily KPIs |
| User Reminders | 10 AM WAT | SMS to inactive users |
| Certificate Generation | 2 AM WAT | Auto-generate certificates |
| Data Cleanup | Sunday 3 AM | NDPA compliance (90 days) |
| Database Backup | 4 AM daily | Automated backups |

### Logs

Logs are stored in:
- Backend: `backend/logs/api_requests.log`
- Celery: `backend/logs/celery.log`
- Nginx: `/var/log/nginx/access.log` and `/var/log/nginx/error.log`

Configure log rotation:
```bash
# /etc/logrotate.d/mnair
/var/www/mnair/backend/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 www-data www-data
}
```

## Scaling Considerations

### Horizontal Scaling

1. **API Servers**: Run multiple Uvicorn workers or instances behind a load balancer
2. **Celery Workers**: Scale workers independently based on task queue length
3. **Database**: Set up PostgreSQL replication (primary + read replicas)
4. **Redis**: Configure Redis Cluster for high availability
5. **MinIO**: Use distributed MinIO setup

### Performance Optimization

1. **CDN**: Use CloudFlare or similar for static assets
2. **Database**: Add indexes for frequently queried fields
3. **Caching**: Implement Redis caching for analytics queries
4. **Rate Limiting**: Use Redis backend for distributed rate limiting

## Backup Strategy

### Automated Backups (via Celery)

- Database backups run daily at 4 AM WAT
- Stored in `/app/backups/` with 30-day retention
- Compressed SQL dumps using `pg_dump`

### Manual Backup

```bash
# Database
pg_dump -h localhost -U mnair_user mnair_production | gzip > backup_$(date +%Y%m%d).sql.gz

# MinIO/S3
mc mirror minio/mnair-certificates ./backups/certificates/
```

## Troubleshooting

### Common Issues

**1. Database connection errors**
- Check PostgreSQL is running: `systemctl status postgresql`
- Verify credentials in `.env`
- Check network connectivity

**2. Celery tasks not running**
- Check Redis connection
- Verify Celery worker and beat are running
- Check task logs for errors

**3. Frontend not connecting to backend**
- Verify API URL in `frontend/.env`
- Check CORS configuration in backend
- Ensure backend is accessible from frontend

**4. Certificate generation fails**
- Check MinIO connectivity
- Verify MinIO bucket exists
- Check write permissions

## Support

For technical support:
- Email: support@mnair.gov.ng
- Documentation: https://docs.mnair.gov.ng
- GitHub Issues: <repository-issues-url>

## License

This platform is built for the Federal Government of Nigeria.

---

**Deployment Checklist:**
- [ ] Environment variables configured
- [ ] Database initialized with admin user
- [ ] Curriculum data loaded (175 lessons)
- [ ] SSL certificates installed
- [ ] Monitoring set up
- [ ] Backups tested
- [ ] Security audit completed
- [ ] Load testing performed
- [ ] Disaster recovery plan documented
- [ ] Team trained on operations

**Production URL:** https://mnair.gov.ng
**API Documentation:** https://api.mnair.gov.ng/docs
