# Connecting to WebDAV with macOS Finder

This guide explains how to connect to the Photo Album WebDAV server using macOS Finder.

## Prerequisites

1. Docker Compose services running:
   ```bash
   docker compose up
   ```

2. A Django user account created:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

## Connect via Finder

### Method 1: Connect to Server Dialog

1. Open Finder
2. Press `Cmd + K` (or menu: Go > Connect to Server...)
3. Enter the server address:
   ```
   http://localhost:8080
   ```
4. Click **Connect**
5. When prompted, select **Registered User**
6. Enter your Django username and password
7. Click **Connect**

The WebDAV share will mount and appear in Finder's sidebar under "Locations".

### Method 2: Finder Menu

1. Open Finder
2. Go to menu: **Go > Connect to Server...**
3. Follow steps 3-7 from Method 1

## Using the Mounted Drive

Once connected, you can:

- **Browse files**: Navigate folders like any local drive
- **Upload files**: Drag and drop files into the Finder window
- **Download files**: Drag files to your local folders or double-click to open
- **Create folders**: Right-click > New Folder (or `Cmd + Shift + N`)
- **Rename**: Click on filename or press Enter to rename
- **Delete**: Move to Trash (`Cmd + Delete`)
- **Copy/Move**: Standard Finder copy/paste operations

## Disconnect

To disconnect from the WebDAV server:

1. In Finder sidebar, right-click the mounted volume
2. Select **Eject** (or press `Cmd + E`)

Alternatively, drag the mounted volume to the Trash.

## Troubleshooting

### "Connection Failed" Error

- Verify Docker services are running: `docker compose ps`
- Check WebDAV service logs: `docker compose logs webdav`
- Ensure port 8080 is not used by another application

### "Authentication Failed" Error

- Verify your username and password are correct
- Check user exists: `docker compose exec web python manage.py shell -c "from django.contrib.auth.models import User; print(list(User.objects.values_list('username', flat=True)))"`
- Ensure user is active (not disabled)

### Slow Performance

- This is normal for development setup with MinIO
- Large file transfers may take longer over WebDAV than direct upload

### Files Not Appearing

- Press `Cmd + R` to refresh Finder
- Check if file was uploaded: `docker compose exec web python manage.py shell -c "from server.apps.files.models import File; print(list(File.objects.values_list('file', flat=True)))"`

## Technical Details

- **Protocol**: WebDAV (HTTP-based)
- **Port**: 8080 (development)
- **Authentication**: HTTP Basic Auth with Django credentials
- **Storage Backend**: MinIO (development) / S3 (production)

## Security Notes

- Development setup uses HTTP (not HTTPS) - suitable only for local development
- Production deployments should use HTTPS with proper certificates
- Each user can only see their own files (multi-tenant isolation)
