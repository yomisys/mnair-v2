# MNAIR Platform - Make Nigeria AI Ready

[![Status](https://img.shields.io/badge/status-operational-brightgreen)]()
[![Completion](https://img.shields.io/badge/completion-92%25-blue)]()
[![Lessons](https://img.shields.io/badge/lessons-175-orange)]()
[![Languages](https://img.shields.io/badge/languages-5-purple)]()

## Overview

The **Make Nigeria AI Ready (MNAIR)** platform is a national AI literacy initiative designed to educate millions of Nigerians about Artificial Intelligence through accessible, localized content delivered via WhatsApp, USSD, and SMS.

### Key Features

- **7-Day AI Literacy Program**: Comprehensive curriculum covering AI basics, ethics, tools, and applications
- **5 Nigerian Languages**: English, Hausa, Igbo, Pidgin, and Yoruba
- **175 Interactive Lessons**: With quizzes and progress tracking
- **Multi-Channel Access**: WhatsApp, USSD (*384*8080#), and SMS
- **Certificate Generation**: Verifiable certificates for program graduates
- **Admin Dashboard**: Analytics, user management, and content oversight
- **NDPA Compliant**: Full compliance with Nigeria Data Protection Act 2023

## Current Status

**Platform Status**: ✅ FULLY OPERATIONAL

- Docker Services: Running (PostgreSQL, Redis, MinIO)
- Backend API: Running at http://localhost:8000
- Frontend: Running at http://localhost:3000
- Database: Initialized with 175 lessons
- Admin Account: Created and ready

## Quick Access

### For Users
- **Home Page**: http://localhost:3000
- **Verify Certificate**: http://localhost:3000/verify

### For Administrators
- **Login**: http://localhost:3000/login
  - Phone: `+2348000000000`
  - Password: `admin123`
- **Dashboard**: http://localhost:3000/dashboard

### For Developers
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Documentation

- **[QUICK_START.md](QUICK_START.md)** - Daily operations and common tasks
- **[DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md)** - Current deployment status and configuration
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete production deployment guide
- **[PROJECT_STATUS.md](PROJECT_STATUS.md)** - Project overview and module status

## Technology Stack

### Backend
- FastAPI (Python 3.8+)
- PostgreSQL 15 (async SQLAlchemy 2.0)
- Redis 7 (caching)
- MinIO (S3-compatible storage)
- Celery + Beat (background tasks)

### Frontend
- React 18 + TypeScript 5
- Material-UI 5
- Vite 4
- React Router 6
- Axios

### Infrastructure
- Docker & Docker Compose
- Nginx (production)
- Ubuntu 20.04+ (production)

## Project Structure

```
mnair/
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── models/      # SQLAlchemy models
│   │   ├── routers/     # API endpoints
│   │   ├── services/    # Business logic
│   │   ├── middleware/  # Security & logging
│   │   └── tasks/       # Celery tasks
│   ├── tests/           # Backend tests
│   └── requirements.txt
├── frontend/            # React application
│   ├── src/
│   │   ├── pages/       # Page components
│   │   ├── components/  # Reusable components
│   │   ├── contexts/    # React contexts
│   │   └── services/    # API client
│   └── package.json
├── curriculum/          # 175 YAML lesson files
│   ├── day1/
│   ├── day2/
│   └── ...
├── docker-compose.yml   # Docker services
└── docs/               # Additional documentation
```

## Curriculum

### 7-Day Program Structure

Each day covers 5 topics across 5 languages (25 lessons/day):

1. **What is AI?** - Introduction to artificial intelligence
2. **How AI Works** - Understanding AI mechanisms
3. **AI in Nigeria** - Local context and applications
4. **AI Tools You Can Use** - Practical AI tools
5. **AI Ethics & Safety** - Responsible AI usage

**Total**: 7 days × 5 topics × 5 languages = **175 lessons**

### Supported Languages
- 🇬🇧 English (en)
- 🇳🇬 Nigerian Pidgin (pid)
- 🇳🇬 Hausa (ha)
- 🇳🇬 Yoruba (yo)
- 🇳🇬 Igbo (ig)

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Node.js 20+
- Python 3.8+

### Installation

1. **Start Docker services**:
   ```bash
   docker-compose up -d
   ```

2. **Set up backend**:
   ```bash
   cd backend
   python -m venv venv
   ./venv/Scripts/activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   pip install -r requirements.txt
   python init_db_simple.py
   python create_admin.py
   python load_curriculum.py
   ```

3. **Start backend**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

4. **Set up frontend**:
   ```bash
   cd frontend
   npm install
   echo "VITE_API_URL=http://localhost:8000" > .env
   ```

5. **Start frontend**:
   ```bash
   npm run dev
   ```

6. **Access the platform**:
   - Frontend: http://localhost:3000
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Development

### Running Tests
```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

### Code Style
- Backend: Follow PEP 8 (use `black` formatter)
- Frontend: ESLint + Prettier

## Security

### Important Notes
- Change default admin password in production
- Update all API keys and secrets
- Enable HTTPS with valid SSL certificates
- Configure CORS for production domains
- Set up database backups
- Review NDPA compliance settings

## License

This platform is developed for the Federal Government of Nigeria.

## Support

For questions or issues:
- Review documentation in the `docs/` folder
- Check `DEPLOYMENT_STATUS.md` for current status
- Consult `QUICK_START.md` for common operations

---

**Platform Version**: 1.0.0  
**Last Updated**: March 26, 2026  
**Deployment Status**: Operational  
**Modules Complete**: 12/13 (92%)
