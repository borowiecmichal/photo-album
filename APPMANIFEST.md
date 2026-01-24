# Cloud Storage Platform - Application Manifest

> **Status**: Specification complete, ready for phased implementation
> **Last updated**: 2026-01-17
> **Version**: 2.0

## Quick Summary

A public cloud storage platform with S3 backend (Cloudflare R2) and Django metadata management. Users access files through native OS file browsers (Finder, Files app, File Explorer) via WebDAV protocol, and through Flutter apps (web, iOS, Android, desktop). Features tagging, file sharing, quotas, and a full REST API.

**Key complexity**: WebDAV protocol server bridging native OS file access with Django ORM and S3 storage, plus Flutter cross-platform apps consuming a REST API.

---

## Project Vision

### From Personal Tool to Public Platform

This project evolves from a personal cloud storage solution to a **public cloud storage platform** supporting:
- Public user signups (with moderation)
- Full file sharing capabilities
- Cross-platform Flutter apps
- Third-party integrations via REST API

### Core Value Proposition

Files stored in cloud storage (S3/R2) are represented as Django model objects, enabling:
- Rich metadata management (tags, search)
- Native OS file browser integration
- Cross-platform Flutter apps
- Developer-friendly API

---

## Target Platforms

### Protocol Server Access (Native File Browsers)
- **macOS**: Finder via WebDAV mounting
- **iOS**: Files app via WebDAV
- **Windows**: File Explorer via WebDAV network drive
- **Android**: Native file managers via WebDAV

### Flutter Apps
- **Web**: Dashboard + basic file browsing
- **iOS**: Native app with dashboard + file management
- **Android**: Native app with dashboard + file management
- **Desktop**: macOS, Windows, Linux apps

---

## Decisions Made

### Protocol & Access
| Decision | Choice | Rationale |
|----------|--------|-----------|
| File access protocol | WebDAV (preferred) | Better Finder integration, fallback to SFTP if issues |
| Path visibility | Hidden user ID | Users see `/documents`, not `/user_123/documents` |
| Concurrent sessions | 5 per user max | Covers typical device count |
| Protocol authentication | App passwords | Separate from Django password, individually revocable |
| Large file downloads | Presigned URLs | Direct S3 download, reduces server load |

### File Operations
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Duplicate filenames | Auto-rename | `photo.jpg`, `photo (1).jpg`, etc. No data loss |
| MIME mismatch | Detect and warn | Log warning but preserve original extension |
| Empty folders | Allow with placeholder | Users can create folders via mkdir |
| Filename handling | ASCII-safe | Convert unicode to safe equivalents for compatibility |
| Path length | 255 characters | Standard limit covers 99% of use cases |
| Hidden files | Filter system files | Skip `.DS_Store`, `Thumbs.db`; keep user dotfiles |
| Symlinks | Follow and log | Upload target file content, log warning |

### Upload & Sync
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Partial uploads | Resumable via Redis | Track chunks in Redis with TTL |
| Redis dependency | Required for uploads | Refuse uploads if Redis down, downloads still work |
| Conflict resolution | Last write wins | Simpler; acceptable for this use case |
| Rename operations | Hybrid | Update DB immediately, background S3 sync via Celery |

### S3 Storage Strategy
| Decision | Choice | Rationale |
|----------|--------|-----------|
| S3 key format | UUID-based | Simplifies rename operations |
| Original path storage | S3 metadata + DB | Redundancy if DB lost |
| Production provider | Cloudflare R2 | No egress fees |
| Encryption | S3 SSE | Let S3/MinIO handle encryption |
| Backup strategy | S3 versioning | Point-in-time recovery via S3 |
| Storage tiers | Single tier (initially) | Auto-archive to cold storage later |

### Deletion & Trash
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Delete behavior | Soft delete + 30-day trash | Recoverable via `/.Trash/` virtual folder |
| Trash visibility | Virtual folder in protocol | Users can browse, restore by moving out |
| Trash quota | Counts against quota | Standard behavior |
| Over quota | Read/delete OK | Only uploads blocked |

### Tagging System
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tag interface | Extended attributes (xattr) | Read/write tags from Finder |
| Finder integration | Color labels + custom property | Both macOS labels AND full tag names |
| Virtual tag folders | Symlink-like | `/Tags/vacation/` shows tagged files; delete removes tag, not file |

### Multi-User & Security
| Decision | Choice | Rationale |
|----------|--------|-----------|
| User signups | Public (eventually) | Email + admin approval initially, email-only later |
| Storage quotas | Hard limits per user | Configurable, enforced |
| Rate limiting | All operations | Uploads, downloads, API calls |
| File type restrictions | Block executables | Reject `.exe`, `.sh`, `.bat`, etc. for public safety |
| Virus scanning | Deferred to Phase 2 | Add ClamAV before public launch |
| Audit logging | Basic now, full model later | Log access events, queryable history eventually |
| Legal docs | Template-based ToS/Privacy | Use open-source templates |
| Account deletion | Full GDPR purge | Delete all data permanently on request |
| Account suspension | 30-day grace period | Read-only access, then lockout, then deletion after 90 days |

### Sharing
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sharing model | Full sharing | User-to-user + public links + folder sharing |
| Permission levels | View / Edit / Full | Owner chooses when sharing |
| Public link controls | Full | Expiry, password, download limit, view count limit |
| Shared folder access | On-demand | Recipients browse via protocol, files stay in owner's quota |

### Thumbnails
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Thumbnail types | Images only (initially) | JPEG, PNG, GIF, WebP, HEIC |
| Generation timing | Background job | Celery task after upload |
| Thumbnail sizes | Small (200px) + Large (800px) | Grid view and preview |
| Storage | Same S3 bucket | `/thumbnails/{file_id}/` prefix |
| Quota | Counts against user | Transparent billing |

### Infrastructure
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Background jobs | Celery + Redis | Industry standard, Redis already needed |
| Database | Single PostgreSQL | Vertical scaling; read replicas if needed later |
| Observability | Structured logging + Prometheus | JSON logs, metrics for monitoring |
| Hosting | Undecided | Design for flexibility (VPS, containers, etc.) |
| Remote access | VPN for admin, public domain for files | Strong auth on public endpoints |

### Frontend & API
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend framework | Flutter | Single codebase for web, iOS, Android, desktop |
| Flutter scope | All platforms from start | Leverage Flutter's cross-platform strength |
| Flutter role | Hybrid | Dashboard + basic file browsing; heavy transfers via protocol |
| API style | REST | Simple, well-understood, good tooling |
| Third-party API | Full API | REST with OAuth, webhooks, rate limiting |
| Admin access | Django Admin for superusers | User dashboard in Phase 2 |
| Marketing | Simple landing page | One-page with features, pricing, signup CTA |

### Migration (Initial Data Import)
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source | Local files (10-100GB) | Medium-size migration |
| Timestamps | Preserve both | Keep original creation and modification dates |
| Error handling | Retry 3x then skip | Log failures, continue with rest |

---

## Implementation Status

### Completed (Phase 1A)
- [x] MinIO Docker setup with health checks
- [x] Django storage backend configuration (django-storages + boto3)
- [x] `files` Django app with models
- [x] File model with user, path, metadata fields
- [x] Tag model with color and user scoping
- [x] Database migrations and indexes
- [x] File operations business logic (upload, download, delete, list)
- [x] Transaction-safe operations with S3 rollback
- [x] Django Admin for files and tags
- [x] Comprehensive test suite with moto S3 mocking

### Completed (Phase 1B)
- [x] WebDAV protocol server (WsgiDAV)
- [x] Django model integration
- [x] Authentication with Django users
- [x] Hidden user ID path mapping
- [x] Session management (5 concurrent limit)
- [x] File/folder operations (GET, PUT, DELETE, MKCOL, MOVE, COPY)
- [x] WebDAV Docker service on port 8080
- [x] Comprehensive test suite (79 tests)

### Not Started
- [ ] App passwords for protocol auth
- [ ] Trash/soft delete system
- [ ] Virtual /.Trash/ folder
- [ ] Extended attributes for tags
- [ ] Virtual /Tags/ folders
- [ ] Resumable uploads with Redis
- [ ] Storage quotas
- [ ] Rate limiting
- [ ] Background S3 sync job (Celery)
- [ ] Thumbnail generation
- [ ] Sharing system
- [ ] REST API
- [ ] Flutter apps
- [ ] User dashboard
- [ ] Landing page
- [ ] Public signup flow

---

## Technical Architecture

### Storage Layer
```
Development: MinIO (local S3-compatible)
Production:  Cloudflare R2 (no egress fees)
Abstraction: Django storage backends (django-storages + boto3)
Encryption:  S3 Server-Side Encryption (SSE)
Backup:      S3 versioning enabled
```

### S3 Key Structure
```
{bucket}/
  files/
    {uuid}/                    # File UUID as folder
      content                  # Actual file content
  thumbnails/
    {file_uuid}/
      small.jpg               # 200px thumbnail
      large.jpg               # 800px thumbnail
```

Original filename stored in:
1. File.storage_path (DB) - canonical source
2. S3 object metadata (x-amz-meta-original-path) - backup

### Data Models

#### File Model (Implemented)
```python
class File(models.Model):
    user = ForeignKey(User)           # Owner
    storage_path = CharField()        # User-visible path: documents/report.pdf
    s3_key = UUIDField()             # Actual S3 key
    size_bytes = BigIntegerField()
    mime_type = CharField()
    checksum_sha256 = CharField()
    uploaded_at = DateTimeField()
    modified_at = DateTimeField()
    original_created_at = DateTimeField()  # Preserved from source
    original_modified_at = DateTimeField() # Preserved from source
    is_deleted = BooleanField()       # Soft delete flag
    deleted_at = DateTimeField()      # When moved to trash
    tags = ManyToManyField(Tag)
```

#### Tag Model (Implemented)
```python
class Tag(models.Model):
    user = ForeignKey(User)
    name = CharField()
    color = CharField()               # Hex color for UI
    finder_label = IntegerField()     # macOS Finder color label (0-7)
    created_at = DateTimeField()
```

#### New Models Needed

```python
class AppPassword(models.Model):
    """Separate passwords for protocol access."""
    user = ForeignKey(User)
    name = CharField()                # e.g., "MacBook Pro"
    password_hash = CharField()
    created_at = DateTimeField()
    last_used_at = DateTimeField()
    is_active = BooleanField()

class Session(models.Model):
    """Track active protocol sessions."""
    user = ForeignKey(User)
    app_password = ForeignKey(AppPassword)
    device_info = CharField()
    ip_address = GenericIPAddressField()
    started_at = DateTimeField()
    last_activity = DateTimeField()

class UserQuota(models.Model):
    """Storage quota per user."""
    user = OneToOneField(User)
    quota_bytes = BigIntegerField()   # e.g., 10GB = 10737418240
    used_bytes = BigIntegerField()

class Share(models.Model):
    """File/folder sharing."""
    file = ForeignKey(File)
    shared_by = ForeignKey(User)
    shared_with = ForeignKey(User, null=True)  # null = public link
    permission = CharField()          # view, edit, full
    token = CharField()               # For public links
    password_hash = CharField()       # Optional password
    expires_at = DateTimeField()
    max_downloads = IntegerField()
    download_count = IntegerField()
    created_at = DateTimeField()

class AuditLog(models.Model):
    """Access audit trail (Phase 2+)."""
    user = ForeignKey(User)
    file = ForeignKey(File)
    action = CharField()              # read, write, delete, share
    ip_address = GenericIPAddressField()
    timestamp = DateTimeField()
    details = JSONField()

class PartialUpload(models.Model):
    """Track resumable uploads (optional, Redis primary)."""
    user = ForeignKey(User)
    upload_id = UUIDField()
    target_path = CharField()
    total_size = BigIntegerField()
    uploaded_bytes = BigIntegerField()
    s3_multipart_id = CharField()
    expires_at = DateTimeField()
```

### File Operation Workflows

#### Upload Flow (Updated)
```
1. User drags file to Finder/WebDAV mount
2. Protocol server receives PUT request
3. Check quota: user.quota.used_bytes + file_size <= quota_bytes
4. Check for duplicate filename, generate unique name if needed
5. Generate UUID for S3 key
6. BEGIN upload:
   a. If resumable (large file):
      - Store upload state in Redis with TTL
      - Use S3 multipart upload
   b. Stream file to S3 at files/{uuid}/content
   c. Calculate SHA256 checksum during stream
   d. Detect MIME type, warn if mismatch with extension
7. BEGIN DB transaction:
   a. Create File object with metadata
   b. Update user quota used_bytes
   c. If fails: Delete from S3 (rollback)
8. Queue thumbnail generation (Celery) if image
9. Return success
```

#### Download Flow (Updated)
```
1. User opens file in Finder
2. Protocol server receives GET request
3. Validate session (check concurrent limit)
4. Check access: file.user == session.user OR valid share
5. If file.size_bytes > 10MB:
   a. Generate presigned S3 URL (15 min expiry)
   b. Redirect client to presigned URL
6. Else: Stream directly from S3
7. Log access (basic audit)
```

#### Delete Flow (Updated)
```
1. User deletes file in Finder
2. Protocol server receives DELETE request
3. BEGIN DB transaction:
   a. Set file.is_deleted = True
   b. Set file.deleted_at = now()
   c. File remains in S3 (soft delete)
4. File appears in /.Trash/ virtual folder
5. After 30 days (background job):
   a. Delete from S3
   b. Delete File record
   c. Update quota used_bytes
```

#### Rename/Move Flow (Updated)
```
1. User renames file in Finder
2. Protocol server receives MOVE request
3. Sanitize new filename (ASCII-safe)
4. Check for duplicates, auto-rename if needed
5. BEGIN DB transaction:
   a. Update file.storage_path
   b. Commit immediately
6. Queue background job (Celery):
   a. Copy S3 object to new key (if path-based keys)
   b. Update S3 metadata with new path
   c. Delete old S3 object
   Note: S3 key is UUID-based, so minimal S3 work needed
```

#### Trash Operations
```
/.Trash/ virtual folder behavior:
- LIST: Query File.objects.filter(user=user, is_deleted=True)
- MOVE out of trash: Set is_deleted=False, deleted_at=None (restore)
- DELETE from trash: Permanent delete (S3 + DB)
- Cannot upload to trash
- Cannot rename in trash
```

### Docker Architecture

```yaml
services:
  postgres:
    image: postgres:18
    # Shared by Django and protocol server

  redis:
    image: redis:7-alpine
    # Session state, resumable uploads, Celery broker

  minio:
    image: minio/minio:latest
    # S3-compatible storage (dev only)

  django:
    # Django web application
    # Ports: 8000 (admin), 8001 (API)

  webdav:
    # WebDAV protocol server
    # Port: 8080 (HTTP) or 8443 (HTTPS)
    # Imports Django models directly

  celery-worker:
    # Background job processor
    # Thumbnail generation, S3 sync, cleanup

  celery-beat:
    # Periodic task scheduler
    # Trash cleanup, orphan cleanup, quota recalc
```

### REST API Structure

```
/api/v1/
  auth/
    POST /login                    # Get JWT token
    POST /logout                   # Invalidate token
    POST /app-passwords            # Create app password
    DELETE /app-passwords/{id}     # Revoke app password

  files/
    GET /                          # List files (with pagination, filters)
    POST /                         # Upload file
    GET /{id}                      # Get file metadata
    GET /{id}/download             # Get download URL
    PUT /{id}                      # Update metadata
    DELETE /{id}                   # Delete (soft)
    POST /{id}/restore             # Restore from trash
    DELETE /{id}/permanent         # Permanent delete

  folders/
    GET /                          # List folder tree
    POST /                         # Create folder
    DELETE /{path}                 # Delete empty folder

  tags/
    GET /                          # List user's tags
    POST /                         # Create tag
    PUT /{id}                      # Update tag
    DELETE /{id}                   # Delete tag
    POST /files/{id}/tags          # Add tag to file
    DELETE /files/{id}/tags/{tag}  # Remove tag

  shares/
    GET /                          # List my shares
    POST /                         # Create share
    GET /{token}                   # Get shared file (public)
    DELETE /{id}                   # Revoke share

  account/
    GET /me                        # Current user info
    GET /quota                     # Quota usage
    PUT /settings                  # Update settings
    DELETE /me                     # Delete account (GDPR)

  trash/
    GET /                          # List trash
    POST /empty                    # Empty all trash
```

### WebDAV Endpoints

```
PROPFIND /                         # List root (user's files)
PROPFIND /{path}                   # List directory
GET /{path}                        # Download file
PUT /{path}                        # Upload file
DELETE /{path}                     # Delete file/folder
MKCOL /{path}                      # Create folder
MOVE /{path}                       # Rename/move
COPY /{path}                       # Copy file

PROPFIND /.Trash/                  # List trash
MOVE /.Trash/{file} → /{path}      # Restore from trash

PROPFIND /Tags/                    # List tags as folders
PROPFIND /Tags/{tag}/              # List files with tag

PROPPATCH /{path}                  # Set extended attributes (tags)
```

---

## Development Phases

### MVP (Alpha Testers)
Core file storage functionality only:
- [x] Django models and storage backend
- [ ] WebDAV protocol server with authentication
- [ ] Basic web dashboard (Flutter web)
- [ ] Storage quotas
- [ ] Soft delete with trash

**Not in MVP**: Sharing, API, tags, thumbnails, mobile apps

### Phase 1: Core Infrastructure

#### 1A: Storage Foundation (Complete)
- [x] MinIO Docker setup
- [x] Django storage backend
- [x] File and Tag models
- [x] Business logic layer
- [x] Django Admin

#### 1B: Protocol Server (Complete)
- [x] WebDAV server implementation (WsgiDAV)
- [x] Django model integration
- [x] Authentication with Django users
- [x] Hidden user ID path mapping
- [x] Session management (5 concurrent limit)
- [ ] App password support (deferred to Phase 2)
- [x] Tests with moto (79 tests)

#### 1C: File Operations
- [ ] Upload with quota check
- [ ] Auto-rename duplicates
- [ ] Download with presigned URLs
- [ ] Soft delete to trash
- [ ] Virtual /.Trash/ folder
- [ ] Restore from trash
- [ ] Permanent delete
- [ ] Rename/move operations
- [ ] Empty folder support

#### 1D: Integration Testing
- [ ] macOS Finder mounting
- [ ] File operations via Finder
- [ ] iOS Files app testing
- [ ] Windows File Explorer testing
- [ ] Performance testing

### Phase 2: User Experience

#### 2A: Tagging System
- [ ] Extended attributes (xattr) support
- [ ] Finder color label mapping
- [ ] Custom tag properties
- [ ] Virtual /Tags/ folders
- [ ] Tag CRUD in admin

#### 2B: Flutter App Foundation
- [ ] Flutter project setup
- [ ] Authentication flow
- [ ] Basic dashboard
- [ ] Quota display
- [ ] File listing (read-only)
- [ ] Build for web, iOS, Android

#### 2C: Background Jobs
- [ ] Celery setup with Redis
- [ ] S3 path sync job
- [ ] Trash cleanup job (30-day)
- [ ] Orphan file cleanup job
- [ ] Quota recalculation job

#### 2D: Thumbnails
- [ ] Image detection on upload
- [ ] Thumbnail generation job
- [ ] Small (200px) and large (800px)
- [ ] Thumbnail API endpoint
- [ ] Flutter integration

### Phase 3: Sharing & API

#### 3A: REST API
- [ ] Django REST Framework setup
- [ ] JWT authentication
- [ ] File CRUD endpoints
- [ ] Tag endpoints
- [ ] Account endpoints
- [ ] Rate limiting
- [ ] API documentation (OpenAPI)

#### 3B: Sharing System
- [ ] Share model and migrations
- [ ] User-to-user sharing
- [ ] Public links with controls
- [ ] Permission levels
- [ ] Share management UI

#### 3C: Flutter Full Features
- [ ] File upload in app
- [ ] File browsing
- [ ] Share management
- [ ] Tag management
- [ ] Offline indicators

### Phase 4: Public Launch Prep

#### 4A: User Management
- [ ] Public signup flow
- [ ] Email verification
- [ ] Admin approval queue
- [ ] Account suspension logic
- [ ] GDPR deletion

#### 4B: Security Hardening
- [ ] Virus scanning (ClamAV)
- [ ] Executable blocking
- [ ] Full audit logging
- [ ] Rate limiting tuning
- [ ] Security audit

#### 4C: Marketing
- [ ] Landing page
- [ ] Terms of Service
- [ ] Privacy Policy
- [ ] Documentation
- [ ] Pricing page (for future paid tiers)

### Phase 5: Future Enhancements
- [ ] Video thumbnails (ffmpeg)
- [ ] Document previews (PDF, Office)
- [ ] Full-text search
- [ ] Auto-archive to cold storage
- [ ] Native mobile push notifications
- [ ] OAuth for API
- [ ] Webhooks
- [ ] Desktop sync client
- [ ] File versioning

---

## Technical Dependencies

### Python Packages (Poetry)

**Core (Installed)**
- django-storages
- boto3
- django-split-settings
- structlog

**To Add**
- wsgidav - WebDAV server
- celery - Background tasks
- redis - Celery broker, session state
- djangorestframework - REST API
- djangorestframework-simplejwt - JWT auth
- python-magic - MIME type detection
- pillow - Thumbnail generation

**Testing (Installed)**
- pytest-django
- moto - S3 mocking

### Docker Services
- postgres:18
- redis:7-alpine
- minio/minio:latest (dev only)

### Flutter Dependencies
- dio - HTTP client
- flutter_secure_storage - Credential storage
- provider/riverpod - State management
- go_router - Navigation

---

## Non-Functional Requirements

- **Security**: S3 SSE, HTTPS, app passwords, rate limiting
- **Performance**: Presigned URLs for large files, Redis caching
- **Reliability**: Transaction safety, soft deletes, S3 versioning
- **Code quality**: wemake-python-styleguide, 100% test coverage
- **Observability**: Structured logging, Prometheus metrics

---

## Migration Plan

### Local Files Import Script

```python
# management/commands/import_files.py
# - Scan source directory
# - For each file:
#   - Check if symlink: follow and log
#   - Skip system files (.DS_Store, Thumbs.db)
#   - Preserve original timestamps
#   - Retry 3x on failure, then skip
#   - Log progress every 100 files
# - Final report: imported, skipped, failed
```

**Estimated data**: 10-100GB, tens of thousands of files

---

## Notes

- Project name "photo-album" is legacy; this is a general-purpose cloud storage platform
- WebDAV preferred but will switch to SFTP if Finder integration proves problematic
- Notifications (email, push) deferred; add when needed
- Offline sync deferred; rely on third-party tools if needed
- Start with alpha testers (5-10), validate before public launch
