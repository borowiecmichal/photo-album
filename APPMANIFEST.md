# Photo Album / Cloud Storage Application - Manifest

> **Status**: Planning complete, ready for implementation
> **Last updated**: 2026-01-12

## Quick Summary

Personal cloud storage with S3 backend and Django metadata management, accessible via native OS file browsers (Finder, Files app, File Explorer) through SFTP/WebDAV. Features tagging, filtering, and multi-user support with user isolation.

**Key complexity**: Custom protocol server (WebDAV/SFTP) that bridges native OS file access with Django models and S3 storage.

## Project Purpose

A personal cloud storage solution with advanced file management capabilities, emphasizing file organization through tagging and filtering. The system stores files in cloud storage (S3 or alternatives) while providing seamless access through native operating system file browsers.

## Core Concept

Files are stored in cloud storage but represented as Django model objects, allowing rich metadata management (tags, categories, etc.) while maintaining compatibility with standard file access protocols (SFTP/WebDAV) for native OS integration.

**Multi-user architecture**: Designed from the start to support multiple users with isolated storage spaces, though initially used by a single user.

## Target Platforms

The application must support file browsing through native OS tools:
- **macOS**: Finder (SFTP/WebDAV mounting)
- **iOS**: Files app (iPadOS and iOS)
- **Windows**: File Explorer (network drive mapping)
- **Android**: Native file managers (SFTP/WebDAV clients)

## Key Features

### Phase 1: Core Infrastructure
- [ ] Cloud storage backend integration (MinIO for local dev, S3-compatible for production)
- [ ] Research and choose protocol (SFTP vs WebDAV) based on cross-platform testing
- [ ] Design protocol server ↔ Django integration architecture
- [ ] Django model representation of files with metadata and user ownership
- [ ] File access protocol server implementation with Django integration
- [ ] File upload/download/delete operations with transaction safety
- [ ] Native OS file browser connectivity (Finder, File Explorer, etc.)
- [ ] User authentication for file protocol access
- [ ] Basic error handling and rollback mechanisms

### Phase 2: Organization & Discovery
- [ ] Tagging system for files
- [ ] Tag-based filtering and search
- [ ] File metadata management (name, type, size, dates, custom attributes)
- [ ] Folder navigation UI (folders are implicit from paths, no separate model)
- [ ] Advanced error handling and retry mechanisms
- [ ] Performance optimizations (caching, query optimization)

### Phase 3: Advanced Features (Future)
- [ ] Custom web UI for file management (optional, backend-focused initially)
- [ ] Advanced search capabilities
- [ ] File versioning
- [ ] Sharing and permissions (if multi-user support needed)
- [ ] Thumbnail generation for images/videos
- [ ] Media gallery views

## Technical Architecture

### Storage Layer
- **Development**: MinIO (local S3-compatible storage)
- **Production options**: Amazon S3, Wasabi, Backblaze B2, DigitalOcean Spaces, or any S3-compatible service
- **Storage abstraction**: Django storage backends (django-storages with boto3) for flexibility
- **Configuration**: Environment-based storage backend selection (MinIO locally, S3 in production)

### File Access Protocol

#### Protocol Options to Evaluate

**SFTP:**
- ✅ Universal support (macOS, iOS, Windows, Android)
- ✅ Secure by default (SSH-based)
- ✅ Better for programmatic access
- ❌ More complex Python implementation (paramiko, twisted)
- ❌ Requires SSH key or password management

**WebDAV:**
- ✅ Easier Python implementation (WsgiDAV)
- ✅ HTTP-based, can integrate with Django WSGI
- ✅ Native support on all platforms
- ❌ macOS Finder can have quirks with WebDAV
- ❌ iOS Files app can be finicky

**Decision criteria:**
- Test both with macOS Finder mounting
- Test with iOS Files app
- Evaluate implementation complexity
- Choose based on ease of integration + compatibility

#### Protocol Server ↔ Django Integration Architecture

**Option A: Shared Database Access (Recommended for Phase 1)**
- Protocol server imports Django models directly
- Both processes access same PostgreSQL database
- ✅ Pro: Direct ORM access, can create/update File objects immediately
- ✅ Pro: Simpler architecture for personal use
- ❌ Con: Protocol server needs Django configuration
- ❌ Con: Need to manage database connection pooling

**Option B: REST API Integration**
- Protocol server calls Django REST API for metadata operations
- ✅ Pro: Clean separation of concerns
- ✅ Pro: Django owns all business logic
- ❌ Con: Need to build REST API first
- ❌ Con: Adds latency to file operations

**Option C: Direct Storage + Background Sync**
- Protocol server only interacts with S3
- Periodic job scans S3, creates/updates File objects
- ✅ Pro: Simplest protocol server implementation
- ✅ Pro: No coupling between services
- ❌ Con: Metadata lag (tags unavailable until sync runs)
- ❌ Con: More complex sync logic

**Option D: Event-Driven (Message Queue)**
- Protocol server publishes events to queue (Redis/RabbitMQ)
- Django worker consumes events and updates database
- ✅ Pro: Real-time updates with clean separation
- ✅ Pro: Good for production scaling
- ❌ Con: Requires message queue infrastructure
- ❌ Con: Most complex architecture

**Phase 1 Decision:** Start with **Option A** (shared database) for simplicity, can refactor to Option B or D later if needed.

### Authentication & Security

**Django User Model**: Standard Django authentication for web/admin access

**File Protocol Authentication (Phase 1 Decision):**
- **Start with**: Direct Django password authentication (simpler for personal use)
- **Future upgrade**: App-specific passwords/tokens (Phase 2 when adding more users)
- Rationale: Personal use doesn't require the complexity of app-specific passwords initially
- Can be added later without significant refactoring

**User isolation**: Each user sees only their own files via path-based filtering (`user_id/...`)

**Permission model**: Owner-based access initially, can extend to sharing/permissions in Phase 3

### Data Model

**File Model**: Django model representing each file
- User (ForeignKey to Django User - owner of the file)
- Storage path/key (e.g., `user123/documents/reports/2024-report.pdf`)
- File name extracted from path
- Metadata (size, mime type, upload date, modified date, checksum)
- Many-to-Many relationship to Tags

**Tag Model**: Flexible tagging system
- Name (unique per user or global)
- Optional color/category
- Many-to-Many relationship to Files

**File organization**: Hierarchical structure via S3-style paths (no separate Folder model)
- Path contains subfolders: `user_id/folder/subfolder/file.ext`
- Folders are implicit, extracted from paths (no explicit Folder Django model)
- Tags provide additional non-hierarchical organization

### File Operation Workflows

#### Upload Flow
```
1. User drags file to Finder/File Explorer
2. Protocol server receives write request
3. BEGIN transaction:
   a. Stream file to S3 using boto3
   b. Calculate checksum during upload (MD5/SHA256)
   c. Extract mime type using python-magic
   d. Create File object in Django DB with metadata
   e. If DB write fails: Delete from S3 (rollback)
4. Return success to client
```

**Error handling:**
- S3 upload fails → Return error to client, no DB entry
- DB write fails → Delete uploaded S3 object, return error
- Partial upload → S3 handles multipart upload cleanup

#### Download Flow
```
1. User opens file in Finder/File Explorer
2. Protocol server receives read request
3. Verify user has access to file (check user_id in path)
4. Stream file from S3 using boto3
5. Return content to client
```

#### Delete Flow
```
1. User deletes file in Finder/File Explorer
2. Protocol server receives delete request
3. BEGIN transaction:
   a. Mark File object as deleted in DB (or delete record)
   b. Delete object from S3
   c. If S3 delete fails: Log for cleanup job, but keep DB deleted
4. Return success to client
```

**Note:** DB delete happens first to prevent orphaned DB records. Orphaned S3 objects can be cleaned up by periodic job.

#### Rename/Move Flow
```
1. User renames or moves file
2. Protocol server receives rename request
3. Update File.storage_path in DB
4. S3 object key remains unchanged (path stored in DB abstracts S3 key)
   OR: Copy object in S3 to new key, delete old key (if S3 path must match)
```

**Decision needed:** Does S3 path need to match DB path, or is DB path just metadata?

#### List Directory Flow
```
1. User browses folder in Finder/File Explorer
2. Protocol server receives list request for path
3. Query File.objects.filter(user=user, path__startswith=folder_path)
4. Return file list with metadata (name, size, modified date)
```

**Performance consideration:** This is a DB query per directory listing. May need caching in Phase 2.

### Docker/Deployment Architecture

**Development environment (docker-compose.yml):**
```yaml
services:
  postgres:
    # PostgreSQL 18 database
    # Shared by Django web app and protocol server

  minio:
    # MinIO S3-compatible storage
    # Accessible on localhost:9000

  django:
    # Django web application
    # Port 8000 for admin interface
    # Access to postgres and minio

  protocol-server:
    # WebDAV or SFTP server
    # Shared database access (imports Django models)
    # Access to postgres and minio
    # Port 8080 (WebDAV) or 2222 (SFTP)
```

**Key considerations:**
- Protocol server needs access to Django settings for database connection
- Both Django and protocol server share same database connection pool config
- MinIO data persisted in Docker volume
- Postgres data persisted in Docker volume

### Technical Dependencies

**Python packages (to be added via Poetry):**

**Core storage:**
- `django-storages` - Django storage backends for S3
- `boto3` - AWS SDK for Python (S3 operations)

**Protocol server (choose one):**
- `WsgiDAV` - WebDAV server (if WebDAV chosen)
- `paramiko` - SFTP/SSH protocol (if SFTP chosen)

**File handling:**
- `python-magic` - MIME type detection
- `python-magic-bin` - libmagic binary for Windows/Mac

**Utilities:**
- `django-extensions` - Useful Django extensions for development

**Testing:**
- `moto` - Mock AWS services for testing S3 operations
- `pytest-django` - Already included in project
- `factory-boy` - Test fixtures (if needed)

**Infrastructure (Docker):**
- MinIO container: `minio/minio:latest`
- PostgreSQL container: `postgres:18` (already configured)

### File Preview & Display
- **Native OS handling**: File previews (images, videos, documents) handled automatically by native OS file browsers (Finder, File Explorer, Files app)
- **No custom preview needed in Phase 1**: SFTP/WebDAV server simply serves file content; OS handles rendering
- **Future enhancement**: Custom web-based preview/gallery interface (Phase 3)

## User Interface Strategy

### Primary Interface (Phase 1)
- Native OS file browsers (Finder, File Explorer, Files app)
- Django Admin for metadata management, tagging

### Secondary Interface (Future)
- Custom web UI (lightweight, backend-developer-friendly)
- Consider admin-based UI enhancements before building custom frontend
- Potential options: Django templates with minimal JS, or REST API + simple frontend

## Decisions Made

1. **Integration architecture**: Option A (shared database access) - Protocol server imports Django models directly
2. **Authentication**: Direct Django password auth for Phase 1, app-specific passwords deferred to Phase 2
3. **Storage backend**: MinIO for development, S3-compatible for production
4. **File organization**: S3-style paths with implicit folders (no Folder model)

## Open Questions / Investigation Needed

These questions must be answered during implementation:

1. **Protocol choice (CRITICAL - Must decide first)**:
   - Test WebDAV with macOS Finder: Does mounting work reliably?
   - Test WebDAV with iOS Files app: Does it support WebDAV servers?
   - Test SFTP with macOS Finder: Does it require third-party tools?
   - Evaluate implementation complexity for both
   - **Decision point**: End of Development Priority #1

2. **S3 path strategy**:
   - Should S3 object key exactly match File.storage_path in DB?
   - Or use UUID-based S3 keys with path stored as metadata only?
   - Trade-off: Human-readable S3 vs simplified rename operations
   - **Decision point**: During File model implementation

3. **Rename/Move behavior**:
   - Should renaming a file in Finder trigger S3 object copy+delete?
   - Or keep S3 key static and only update DB path?
   - Impact on performance and S3 costs
   - **Decision point**: During protocol server implementation

4. **Directory listing performance**:
   - Cache file listings in Redis/memory?
   - Or rely on database query optimization (indexes)?
   - Defer to Phase 2 if not a bottleneck
   - **Decision point**: After testing with realistic file counts

5. **Production storage** (Deferred to production deployment):
   - Evaluate S3, Wasabi, Backblaze B2, DigitalOcean Spaces
   - Cost comparison for ~100GB-1TB storage
   - **Decision point**: Before production deployment

## Non-Functional Requirements

- **Security**: Encrypted storage, secure file transfer protocols
- **Performance**: Fast file browsing, efficient metadata queries
- **Reliability**: Data consistency between storage and database
- **Code quality**: Maintain wemake-python-styleguide standards (per CLAUDE.md)
- **Testing**: 100% test coverage requirement

## Development Priorities

### Phase 1A: Storage Foundation (Week 1-2)

1. **Set up MinIO with Docker**
   - Add MinIO service to docker-compose.yml
   - Configure MinIO with default bucket
   - Add health checks and volume persistence
   - Test S3 API access with boto3

2. **Install and configure Django storage backend**
   - Add django-storages, boto3 to Poetry dependencies
   - Configure settings for MinIO (development) and S3 (production)
   - Create environment-based storage backend selection
   - Write tests for storage backend configuration

3. **Create Django app for file management**
   - Create `files` app in server/apps/
   - Set up basic app structure (models, admin, etc.)
   - Add app to INSTALLED_APPS

4. **Implement File model**
   - Define File model with user, path, metadata fields
   - Add database indexes for performance (user, path prefix)
   - Create and run migrations
   - Write model tests (100% coverage)
   - Configure File model in Django Admin

### Phase 1B: Protocol Research & Decision (Week 2)

5. **Protocol evaluation and testing**
   - Research: WebDAV with WsgiDAV library
   - Research: SFTP with paramiko library
   - Create proof-of-concept: Simple WebDAV server
   - Create proof-of-concept: Simple SFTP server
   - Test macOS Finder mounting with both protocols
   - Test iOS Files app connectivity (if possible)
   - **Make decision**: Choose SFTP or WebDAV based on results
   - Document decision rationale in APPMANIFEST.md

### Phase 1C: Protocol Server Implementation (Week 3-4)

6. **Implement protocol server**
   - Create protocol server Python module
   - Set up Django settings import in protocol server
   - Implement authentication (Django User password validation)
   - Implement user isolation (path-based filtering)
   - Add protocol server to docker-compose.yml
   - Configure shared database access

7. **Implement core file operations**
   - **Upload**: Stream to S3 → Create File in DB with transaction safety
   - **Download**: Stream from S3 with access control
   - **Delete**: Delete from DB → Delete from S3 with error handling
   - **List directory**: Query Files by path prefix
   - **Rename/Move**: Implement chosen strategy (update DB path vs S3 copy)
   - Add python-magic for MIME type detection
   - Add checksum calculation during upload

8. **Write tests for protocol server**
   - Mock S3 operations with moto
   - Test upload/download/delete flows
   - Test authentication and authorization
   - Test error handling and rollback
   - Test user isolation
   - Achieve 100% coverage

### Phase 1D: Integration Testing (Week 4-5)

9. **Test with native OS file browsers**
   - Mount protocol server in macOS Finder
   - Test file upload via drag-and-drop
   - Test file download/opening
   - Test file deletion
   - Test file rename/move
   - Test folder creation and navigation
   - Document any quirks or limitations

10. **Verify Django integration**
    - Confirm File objects created in Django Admin after upload
    - Verify metadata accuracy (size, mime type, checksum)
    - Test user isolation in multi-user scenario
    - Check database performance with realistic file counts

### Phase 2: Tagging System (Week 5-6)

11. **Implement Tag model**
    - Create Tag model with name, color, user fields
    - Add Many-to-Many relationship with File
    - Create and run migrations
    - Configure Tag model in Django Admin
    - Write model tests

12. **Add tagging interface in Django Admin**
    - Add inline tags to File admin
    - Add tag filtering to File list view
    - Add tag-based search
    - Create tag management interface
    - Test tagging functionality end-to-end

### Phase 2+: Future Work

13. **Performance optimizations** (as needed)
    - Add caching for directory listings
    - Optimize database queries with select_related/prefetch_related
    - Add database indexes as needed

14. **Advanced features** (Phase 3)
    - Custom web UI for file browsing
    - Advanced search (full-text, metadata filters)
    - File versioning
    - Sharing and permissions
    - Thumbnail generation

## Notes

- Project name "photo-album" may be misleading - this is a general-purpose cloud storage with file management, not limited to photos
- Backend-focused approach: prioritize functionality over UI polish
- Extensibility is key: design for multiple storage backends, potential UI options later