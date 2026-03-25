# Make Nigeria AI Ready (MNAIR)

A national AI literacy platform designed to onboard 10 million Nigerians to AI fundamentals through WhatsApp, USSD, and SMS.

## 🇳🇬 Project Overview

MNAIR is a free, 7-day AI training program optimized for Nigeria's infrastructure constraints:
- **Multi-channel delivery**: WhatsApp, USSD (*384*8080#), SMS fallback
- **5 languages**: English, Pidgin, Hausa, Yoruba, Igbo
- **Low bandwidth**: Works on 2G/3G networks
- **Offline-first**: Lessons cached for unreliable connectivity
- **Free certification**: PDF certificates with blockchain verification

## 🏗️ Architecture

```
mnair/
├── backend/              # FastAPI + PostgreSQL + Redis
│   ├── app/
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── schemas/     # Pydantic validation schemas
│   │   ├── routers/     # API endpoints
│   │   ├── services/    # Business logic
│   │   ├── channels/    # WhatsApp, USSD, SMS handlers
│   │   ├── curriculum/  # Lesson loader & state manager
│   │   ├── tasks/       # Celery background tasks
│   │   ├── certificates/# PDF generation
│   │   └── analytics/   # KPI tracking
│   ├── migrations/      # Alembic database migrations
│   └── tests/           # Pytest test suite
├── frontend/            # React + TypeScript admin dashboard
│   └── src/
│       ├── pages/       # Dashboard, Analytics, Learners, etc.
│       ├── components/  # Reusable UI components
│       └── api/         # API client
├── curriculum/          # 35 YAML lesson files (7 days × 5 topics)
│   ├── day1/
│   ├── day2/
│   └── ...
├── k8s/                 # Kubernetes manifests (for production)
└── monitoring/          # Prometheus + Grafana configs
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### Step 1: Clone and Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd mnair

# Copy environment file and fill in your API keys
cp .env.example .env
# Edit .env with your Termii, Africa's Talking, and Meta API keys
```

### Step 2: Start Infrastructure

```bash
# Start PostgreSQL, Redis, and MinIO
docker compose up -d db redis minio

# Verify services are running
docker compose ps

# Check database connection
docker compose exec db psql -U mnair -c "\\dt"
```

### Step 3: Test MinIO Access

```bash
# MinIO Console: http://localhost:9001
# Login: minioadmin / minioadmin
# Create bucket: mnair-certificates
```

## 📋 Development Workflow

### Module-by-Module Build Plan

Follow this sequence for building with Claude:

#### Phase A — Foundation (Days 1-3)
1. **Module 0**: Database models + docker-compose.yml
2. **Module 1**: Curriculum YAML files + loader service
3. **Module 3**: Lesson state manager + quiz engine

#### Phase B — Channels (Days 4-6)
4. **Module 2A**: WhatsApp webhook + conversation state machine
5. **Module 2B**: USSD handler (Africa's Talking)
6. **Module 2C**: SMS fallback + certificate generator

#### Phase C — API & Frontend (Days 7-12)
7. **Module 5A**: Auth + Core API (FastAPI routers)
8. **Module 5B**: Analytics + Employer API
9. **Module 6A**: Admin dashboard (React)
10. **Module 6B**: Remaining admin pages

#### Phase D — Hardening (Days 13-15)
11. **Modules 7 & 8**: Public landing + certificate verification
12. **Module 10**: Security & NDPA compliance
13. **Module 9 + 11**: Monitoring + final tests

### Golden Rules for Building with Claude

1. **One module per conversation** — Never mix modules
2. Start each conversation with:
   - The module specification
   - Any existing files the module depends on
3. Test each module before moving to the next
4. Run the full test suite after every 2-3 modules

## 🧪 Testing

```bash
# Install backend dependencies
cd backend
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_curriculum.py -v
```

## 📦 Backend Dependencies

Key libraries:
- **FastAPI**: API framework
- **SQLAlchemy**: ORM
- **Alembic**: Database migrations
- **Celery**: Background tasks
- **Redis**: Caching & message broker
- **Pydantic**: Data validation
- **Pytest**: Testing
- **ReportLab**: PDF certificate generation
- **httpx**: HTTP client for webhooks

## 🎨 Frontend Stack

- **React 18** + **TypeScript**
- **Vite**: Build tool
- **Tailwind CSS**: Styling
- **Recharts**: Charts & visualizations
- **React Query**: Server state management
- **Monaco Editor**: In-browser code editor for lessons

## 🔐 Security & Compliance

- **NDPA Compliant**: Nigeria Data Protection Act 2023
- **JWT Authentication**: Role-based access control (admin, employer, learner)
- **Rate Limiting**: 60 req/min per IP
- **Webhook Signature Validation**: Meta & Africa's Talking
- **Data Retention**: 90-day automatic deletion
- **Consent Management**: Explicit opt-in required

## 🌍 Nigerian-Specific Features

1. **Multi-language**: English, Pidgin, Hausa, Yoruba, Igbo
2. **USSD Code**: *384*8080# (Africa's Talking)
3. **SMS Provider**: Termii (Nigerian SMS gateway)
4. **WhatsApp Business**: Meta API via Termii
5. **Low Bandwidth**: All images <50KB, no videos
6. **Telco-Aware**: MTN, Glo, Airtel, 9mobile detection

## 📊 Monitoring

- **Prometheus**: Metrics collection (port 9090)
- **Grafana**: Dashboards (port 3001)
- **Key Metrics**:
  - Active learners (7-day, 30-day)
  - Completion rate per day
  - Channel distribution (WhatsApp vs USSD vs SMS)
  - Average quiz score
  - Certificate issuance rate

## 🛠️ Useful Commands

```bash
# Backend
cd backend
uvicorn app.main:app --reload  # Start API server

# Frontend
cd frontend
npm install
npm run dev  # Start dev server

# Database
docker compose exec db psql -U mnair  # Access PostgreSQL
alembic upgrade head  # Run migrations

# Celery
celery -A app.tasks.celery_app worker --loglevel=info  # Start worker
celery -A app.tasks.celery_app beat --loglevel=info    # Start scheduler

# Docker
docker compose up -d          # Start all services
docker compose down           # Stop all services
docker compose logs -f backend  # View backend logs
```

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

This is a national infrastructure project. Contributions should align with Nigeria's digital transformation goals.

## 📞 Support

For issues related to:
- **API Keys**: Contact Termii or Africa's Talking support
- **Infrastructure**: Check docker-compose.yml health checks
- **NDPA Compliance**: Review app/utils/ndpa_compliance.py

---

**Built with ❤️ for Nigeria's AI future**
