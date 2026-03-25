# MNAIR Platform - Security Documentation

## Overview

This document outlines the security measures implemented in the MNAIR (Make Nigeria AI Ready) platform to protect user data, prevent attacks, and ensure NDPA compliance.

## Security Features Implemented

### 1. Authentication & Authorization

#### JWT Authentication
- **Library**: `python-jose` with RSA/HMAC signatures
- **Token Expiration**: 7 days (10,080 minutes)
- **Token Storage**: Bearer token in Authorization header
- **Refresh Mechanism**: Not implemented (users re-authenticate after 7 days)

#### Password Security
- **Hashing Algorithm**: bcrypt with 10 rounds
- **Library**: `passlib` with bcrypt backend
- **Admin Passwords**: Required for admin accounts
- **Learner Accounts**: Passwordless (phone number only)

#### Role-Based Access Control (RBAC)
- **Roles**: learner, admin, employer
- **Admin-only endpoints**: Analytics dashboard, user management
- **Employer endpoints**: Certificate search and verification
- **Public endpoints**: Certificate verification (no auth required)

### 2. Rate Limiting

#### Implementation
- **Library**: `slowapi` (Flask-Limiter port for FastAPI)
- **Key Function**: IP address or user ID (authenticated users)
- **Storage**: In-memory (for MVP, should use Redis for production)

#### Rate Limits by Endpoint Type

| Endpoint Type | Limit | Purpose |
|--------------|-------|---------|
| Default API | 60/minute | General API protection |
| Authentication (login/register) | 5/minute | Prevent brute force attacks |
| Public (certificate verification) | 30/minute | Allow public access while preventing abuse |
| Quiz Submission | 10/minute | Prevent spam submissions |
| Certificate Generation | 3/minute | Limit expensive PDF operations |
| WhatsApp/USSD Webhooks | 300/minute | Handle high-volume webhook traffic |

#### Custom Rate Limit Handler
```python
# Returns JSON with rate limit details
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please try again later.",
  "detail": "5 per 1 minute"
}
```

### 3. Security Headers

All API responses include the following security headers:

#### X-Content-Type-Options
- **Value**: `nosniff`
- **Purpose**: Prevents MIME type sniffing attacks

#### X-Frame-Options
- **Value**: `SAMEORIGIN`
- **Purpose**: Prevents clickjacking by allowing framing only from same origin

#### X-XSS-Protection
- **Value**: `1; mode=block`
- **Purpose**: Enables XSS filter in older browsers

#### Strict-Transport-Security (HSTS)
- **Value**: `max-age=31536000; includeSubDomains`
- **Purpose**: Enforces HTTPS connections (production only)
- **Note**: Only enabled when `APP_ENV=production`

#### Content-Security-Policy (CSP)
```
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
font-src 'self' data:;
connect-src 'self';
frame-ancestors 'self';
base-uri 'self';
form-action 'self';
```
- **Purpose**: Restricts resource loading to prevent XSS attacks
- **Note**: `unsafe-inline` allowed for Swagger/ReDoc documentation

#### Referrer-Policy
- **Value**: `strict-origin-when-cross-origin`
- **Purpose**: Controls referrer information leakage

#### Permissions-Policy
- **Disabled Features**: accelerometer, camera, geolocation, gyroscope, magnetometer, microphone, payment, usb
- **Purpose**: Disable unnecessary browser features

### 4. Input Validation & Sanitization

#### Request Body Size Limit
- **Maximum**: 10MB per request
- **Response**: 413 Payload Too Large

#### SQL Injection Prevention
- **Method**: Parameterized queries via SQLAlchemy ORM
- **Pattern Detection**: Regex patterns for common SQL injection attempts
- **Patterns Detected**:
  - UNION SELECT statements
  - INSERT INTO, UPDATE SET, DELETE FROM
  - DROP TABLE commands
  - Comment-based injections (`;--`)
  - Boolean-based injections (`' OR '1'='1`)

#### XSS Prevention
- **Pattern Detection**: Regex patterns for script injection
- **Patterns Detected**:
  - `<script>` tags
  - `javascript:` protocol
  - Event handlers (`onclick=`, `onerror=`, etc.)
  - `<iframe>`, `<object>`, `<embed>` tags

#### Path Traversal Prevention
- **Pattern Detection**: Directory traversal attempts
- **Patterns Detected**:
  - `../` and `..\\`
  - URL-encoded variants (`%2e%2e`)

#### Command Injection Prevention
- **Status**: Disabled by default (too many false positives)
- **Note**: Can be enabled in `main.py` if needed

### 5. CORS (Cross-Origin Resource Sharing)

#### Configuration
```python
allow_origins: ["http://localhost:3000", "https://mnair.gov.ng"]  # From settings
allow_credentials: True
allow_methods: ["GET", "POST", "PUT", "DELETE", "PATCH"]
allow_headers: ["Authorization", "Content-Type"]
expose_headers: ["X-Total-Count"]  # For pagination
max_age: 3600  # Cache preflight for 1 hour
```

#### Production Setup
- Update `CORS_ORIGINS` in `.env` to include production domains
- Remove wildcard `*` origins
- Use HTTPS-only origins

### 6. Request Logging

#### What's Logged
- Request method and path
- Request duration
- Response status code
- User ID (if authenticated)
- Client IP address
- User agent
- Errors and exceptions (with stack traces)

#### Log Levels
- **INFO**: Successful requests (2xx, 3xx)
- **WARNING**: Client errors (4xx)
- **ERROR**: Server errors (5xx), exceptions

#### Log Files
- **Location**: `logs/api_requests.log`
- **Format**: Timestamp, logger name, level, message
- **Rotation**: Not implemented (should use `RotatingFileHandler` for production)

#### Privacy Considerations
- Request/response bodies NOT logged by default
- Can be enabled with `log_body=True` (not recommended)
- Sensitive data (passwords, tokens) should never be logged

### 7. Data Privacy & NDPA Compliance

#### Data Retention
- **Conversations**: 90 days (configurable via `DATA_RETENTION_DAYS`)
- **User Records**: Retained indefinitely for completion tracking
- **Lesson Progress**: Retained indefinitely
- **Database Backups**: 30 days

#### Consent Tracking
- `consent_given` field in User model (required for registration)
- `consent_date` timestamp
- NDPA privacy notice must be shown before registration

#### Data Access
- Users can access their own data via `/api/v1/auth/me`
- Admins can access aggregate analytics (no PII)
- Employers can search certificates (limited fields)

#### Data Deletion
- Automated deletion of old conversations (weekly task)
- Manual deletion requests should be handled by admins
- Soft deletion (set `is_active=False`) for inactive users

### 8. Webhook Security

#### WhatsApp Webhook
- **Signature Verification**: HMAC-SHA256 with app secret
- **Header**: `X-Hub-Signature-256`
- **Algorithm**: SHA-256 HMAC of raw request body
- **Rejection**: Invalid signatures rejected with 403 Forbidden

#### USSD Session Security
- **Session Storage**: Redis with 90-second timeout
- **Session Key**: User phone number + session ID
- **Cleanup**: Automatic expiration via Redis TTL

#### SMS Notifications
- **API Key**: Termii API key in environment variables
- **Rate Limiting**: Applied to prevent SMS spam
- **Consent Check**: Only sends to users with `consent_given=True`

### 9. Certificate Security

#### Certificate ID Format
- **Pattern**: `MNAIR-{YEAR}-{USER_ID}-{RANDOM_6_CHARS}`
- **Example**: `MNAIR-2024-00123-A7B9C2`
- **Uniqueness**: Enforced by database unique constraint

#### PDF Verification
- **SHA-256 Hash**: Stored in database for integrity verification
- **Hash Verification**: Compare stored hash with generated hash
- **Tamper Detection**: Hash mismatch indicates certificate modification

#### Storage Security
- **Service**: MinIO (S3-compatible)
- **Access**: Pre-signed URLs with 7-day expiration
- **Bucket**: Private (not public-readable)
- **Download**: Authenticated users only

#### Public Verification
- **Endpoint**: `/api/v1/certificates/verify/{certificate_id}` (no auth)
- **Returns**: Certificate details (learner name, completion date, score)
- **Does NOT return**: PDF file (download requires authentication)

## Security Best Practices

### Environment Variables
- ✅ All secrets stored in `.env` file (not committed to git)
- ✅ `.env.example` provided without real secrets
- ✅ `python-dotenv` used for loading environment variables

### Database Security
- ✅ PostgreSQL with SSL (recommended for production)
- ✅ Parameterized queries (SQLAlchemy ORM)
- ✅ Database credentials in environment variables
- ✅ Connection pooling with limits

### API Keys
- ✅ API keys stored in environment variables
- ✅ Never logged or exposed in responses
- ✅ Separate keys for dev/staging/production

### Error Handling
- ✅ Generic error messages for users (don't expose internals)
- ✅ Detailed errors logged server-side
- ✅ Stack traces only in development mode

## Known Limitations & Future Improvements

### Current Limitations
- ⚠️ Rate limiting uses in-memory storage (won't work with multiple instances)
- ⚠️ No IP whitelisting for admin endpoints
- ⚠️ No 2FA/MFA for admin accounts
- ⚠️ No audit logging for sensitive operations
- ⚠️ No encryption at rest for database
- ⚠️ Log rotation not implemented

### Recommended Improvements
1. **Rate Limiting**: Use Redis backend for distributed rate limiting
2. **Admin Security**: Add 2FA for admin accounts
3. **Audit Logging**: Log all admin actions (user creation, certificate generation, etc.)
4. **Database Encryption**: Enable PostgreSQL encryption at rest
5. **Log Management**: Implement log rotation and centralized logging (ELK stack)
6. **WAF**: Add Web Application Firewall (Cloudflare, AWS WAF)
7. **DDoS Protection**: Use Cloudflare or similar CDN
8. **Vulnerability Scanning**: Regular dependency audits (`pip-audit`, Snyk)
9. **Penetration Testing**: Annual security audits
10. **Incident Response**: Document incident response procedures

## Security Checklist for Production

### Pre-Deployment
- [ ] Change all default secrets and API keys
- [ ] Enable HSTS (`APP_ENV=production`)
- [ ] Update CORS origins to production domains only
- [ ] Configure Redis for rate limiting
- [ ] Enable PostgreSQL SSL
- [ ] Set up database backups
- [ ] Configure log rotation
- [ ] Review and update CSP headers
- [ ] Test rate limiting with load tests
- [ ] Run security scan (`pip-audit`)

### Post-Deployment
- [ ] Monitor error logs for suspicious activity
- [ ] Set up alerting for rate limit violations
- [ ] Review access logs weekly
- [ ] Test certificate verification
- [ ] Verify NDPA compliance automation
- [ ] Test backup restoration
- [ ] Document incident response procedures
- [ ] Schedule security audits

## Reporting Security Issues

If you discover a security vulnerability, please report it to:
- **Email**: security@mnair.gov.ng (example)
- **PGP Key**: [Provide if available]

Please do NOT open public GitHub issues for security vulnerabilities.

## Compliance

### NDPA (Nigeria Data Protection Act)
- ✅ Consent tracking before data collection
- ✅ 90-day data retention for conversations
- ✅ User data access via API
- ✅ Data deletion automation
- ✅ Privacy-by-design approach

### Additional Regulations
- **GDPR**: Consider GDPR if serving EU citizens
- **CCPA**: Consider CCPA if serving California residents

---

**Last Updated**: 2024-01-26
**Version**: 1.0
**Module**: 10 - Security & NDPA Compliance
