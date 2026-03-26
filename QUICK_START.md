# MNAIR Platform - Quick Start Guide

## Starting the Platform

### 1. Start Docker Services (if not running)
```bash
cd /c/Users/yomis/mnair
docker-compose up -d
```

### 2. Start Backend API
```bash
cd /c/Users/yomis/mnair/backend
./venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Or run in background and continue working.

### 3. Start Frontend
```bash
cd /c/Users/yomis/mnair/frontend
npm run dev
```

## Accessing the Platform

### Public Access
- **Home Page**: http://localhost:3000
- **Verify Certificate**: http://localhost:3000/verify

### Admin Access
- **Login**: http://localhost:3000/login
  - Phone: `+2348000000000`
  - Password: `admin123`
- **Dashboard**: http://localhost:3000/dashboard

### Developer Tools
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **MinIO Console**: http://localhost:9001

## Common Tasks

### Check Service Status
```bash
# Docker services
docker ps

# Backend health
curl http://localhost:8000/health

# Database records
cd /c/Users/yomis/mnair/backend
./venv/Scripts/python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models import User, Lesson
from sqlalchemy import select, func

async def check():
    async with AsyncSessionLocal() as db:
        users = await db.execute(select(func.count(User.id)))
        lessons = await db.execute(select(func.count(Lesson.id)))
        print(f'Users: {users.scalar()}')
        print(f'Lessons: {lessons.scalar()}')

asyncio.run(check())
"
```

### Stop Services
```bash
# Stop Docker (keeps containers)
docker-compose stop

# Stop and remove containers
docker-compose down

# Backend & Frontend: Press Ctrl+C in their terminal windows
```

### Reset Database
```bash
cd /c/Users/yomis/mnair/backend
./venv/Scripts/python init_db_simple.py
./venv/Scripts/python create_admin.py
./venv/Scripts/python load_curriculum.py
```

## Troubleshooting

### Backend won't start
- Check if port 8000 is available
- Verify Docker services are running
- Check backend/.env file exists

### Frontend won't start
- Run `npm install` in frontend directory
- Check if port 3000 is available
- Verify frontend/.env file exists with VITE_API_URL

### Database connection errors
- Verify PostgreSQL container is running: `docker ps`
- Check DATABASE_* variables in backend/.env
- Test connection: `docker exec mnair_postgres pg_isready`

### Cannot login to admin
- Verify admin user exists (run create_admin.py)
- Check credentials: +2348000000000 / admin123
- Check browser console for errors

## File Locations

```
mnair/
├── backend/
│   ├── app/              # Application code
│   ├── venv/             # Python virtual environment
│   ├── .env              # Backend configuration
│   ├── init_db_simple.py # Database initialization
│   ├── create_admin.py   # Create admin user
│   └── load_curriculum.py# Load lessons
├── frontend/
│   ├── src/              # React source code
│   ├── .env              # Frontend configuration
│   └── package.json      # Dependencies
├── curriculum/           # 175 YAML lesson files
├── docker-compose.yml    # Docker services config
├── DEPLOYMENT_GUIDE.md   # Full deployment docs
├── DEPLOYMENT_STATUS.md  # Current status
└── QUICK_START.md        # This file
```

## Admin Credentials

**Default Admin Account** (CHANGE IN PRODUCTION):
- Phone: `+2348000000000`
- Password: `admin123`
- Role: Admin
- Access: Full platform access

## Platform URLs Reference

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | http://localhost:3000 | Public site |
| Backend API | http://localhost:8000 | REST API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Health Check | http://localhost:8000/health | System status |
| PostgreSQL | localhost:5433 | Database |
| Redis | localhost:6380 | Cache |
| MinIO API | localhost:9000 | Object storage |
| MinIO Console | localhost:9001 | Storage admin |

## Need Help?

- Full deployment guide: `DEPLOYMENT_GUIDE.md`
- Deployment status: `DEPLOYMENT_STATUS.md`
- Project overview: `PROJECT_STATUS.md`
- API documentation: http://localhost:8000/docs
