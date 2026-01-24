#!/bin/bash
# WebDAV Manual Testing Script
#
# Usage: ./scripts/test_webdav.sh [username] [password]
#
# Prerequisites:
#   - Docker Compose services running: docker compose up
#   - A Django user created: docker compose exec web python manage.py createsuperuser

set -e

USER="${1:-admin}"
PASS="${2:-admin}"
BASE_URL="http://localhost:8080"

echo "Testing WebDAV server at $BASE_URL with user: $USER"
echo "=============================================="
echo ""

# 1. PROPFIND - List root folder
echo "=== 1. PROPFIND - List root folder ==="
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/" -H "Depth: 1" | xmllint --format - 2>/dev/null || \
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/" -H "Depth: 1"
echo ""
echo ""

# 2. PUT - Upload a file
echo "=== 2. PUT - Upload a file ==="
curl -s -u "$USER:$PASS" -X PUT "$BASE_URL/test.txt" -d "Hello WebDAV World" -w "HTTP Status: %{http_code}\n"
echo ""

# 3. GET - Download the file
echo "=== 3. GET - Download the file ==="
echo -n "Content: "
curl -s -u "$USER:$PASS" "$BASE_URL/test.txt"
echo ""
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" -u "$USER:$PASS" "$BASE_URL/test.txt"
echo ""

# 4. PROPFIND - List root with file
echo "=== 4. PROPFIND - List root (should show test.txt) ==="
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/" -H "Depth: 1" | xmllint --format - 2>/dev/null | grep -E "(href|displayname|getcontentlength)" || \
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/" -H "Depth: 1" | grep -E "(href|displayname)"
echo ""

# 5. MKCOL - Create a folder
echo "=== 5. MKCOL - Create documents/ folder ==="
curl -s -u "$USER:$PASS" -X MKCOL "$BASE_URL/documents/" -w "HTTP Status: %{http_code}\n"
echo ""

# 6. MOVE - Move file to folder
echo "=== 6. MOVE - Move test.txt to documents/test.txt ==="
curl -s -u "$USER:$PASS" -X MOVE "$BASE_URL/test.txt" \
    -H "Destination: $BASE_URL/documents/test.txt" \
    -w "HTTP Status: %{http_code}\n"
echo ""

# 7. PROPFIND - List documents folder
echo "=== 7. PROPFIND - List documents/ folder ==="
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/documents/" -H "Depth: 1" | xmllint --format - 2>/dev/null | grep -E "(href|displayname)" || \
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/documents/" -H "Depth: 1" | grep -E "(href|displayname)"
echo ""

# 8. COPY - Copy file back to root
echo "=== 8. COPY - Copy documents/test.txt to /copy.txt ==="
curl -s -u "$USER:$PASS" -X COPY "$BASE_URL/documents/test.txt" \
    -H "Destination: $BASE_URL/copy.txt" \
    -w "HTTP Status: %{http_code}\n"
echo ""

# 9. GET - Verify copy exists
echo "=== 9. GET - Verify copy.txt exists ==="
echo -n "Content: "
curl -s -u "$USER:$PASS" "$BASE_URL/copy.txt"
echo ""
echo ""

# 10. DELETE - Delete the copy
echo "=== 10. DELETE - Delete copy.txt ==="
curl -s -u "$USER:$PASS" -X DELETE "$BASE_URL/copy.txt" -w "HTTP Status: %{http_code}\n"
echo ""

# 11. DELETE - Delete the moved file
echo "=== 11. DELETE - Delete documents/test.txt ==="
curl -s -u "$USER:$PASS" -X DELETE "$BASE_URL/documents/test.txt" -w "HTTP Status: %{http_code}\n"
echo ""

# 12. Final PROPFIND - Verify clean state
echo "=== 12. PROPFIND - Final state (should be empty or minimal) ==="
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/" -H "Depth: 1" | xmllint --format - 2>/dev/null | grep -E "(href|displayname)" || \
curl -s -u "$USER:$PASS" -X PROPFIND "$BASE_URL/" -H "Depth: 1" | grep -E "(href|displayname)"
echo ""

echo "=============================================="
echo "WebDAV testing complete!"
echo ""
echo "Expected HTTP status codes:"
echo "  - 200 OK: Successful GET, PROPFIND"
echo "  - 201 Created: Successful PUT, MKCOL, MOVE, COPY"
echo "  - 204 No Content: Successful DELETE"
echo "  - 207 Multi-Status: PROPFIND response"
echo "  - 401 Unauthorized: Invalid credentials"
echo "  - 404 Not Found: Resource doesn't exist"
echo "  - 409 Conflict: Parent folder doesn't exist"
