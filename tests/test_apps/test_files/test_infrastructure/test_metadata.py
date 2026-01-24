"""Tests for metadata utilities."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from server.apps.files.infrastructure.metadata import (
    calculate_checksum,
    detect_mime_type,
    extract_filename,
    extract_folder_path,
    get_file_extension,
    validate_storage_path,
)


def test_detect_mime_type():
    """Test MIME type detection from filename."""
    file_obj = ContentFile(b'content')

    assert detect_mime_type(file_obj, 'test.pdf') == 'application/pdf'
    assert detect_mime_type(file_obj, 'test.txt') == 'text/plain'
    assert detect_mime_type(file_obj, 'test.jpg') == 'image/jpeg'
    assert detect_mime_type(file_obj, 'test.png') == 'image/png'


def test_detect_mime_type_unknown():
    """Test MIME type detection for unknown extension."""
    file_obj = ContentFile(b'content')

    result = detect_mime_type(file_obj, 'test.unknown')
    assert result == 'application/octet-stream'


def test_calculate_checksum():
    """Test SHA256 checksum calculation."""
    file_obj = ContentFile(b'test content')

    checksum = calculate_checksum(file_obj)

    # Should be 64 character hex string
    assert len(checksum) == 64
    assert all(c in '0123456789abcdef' for c in checksum)

    # Same content should produce same checksum
    file_obj2 = ContentFile(b'test content')
    assert calculate_checksum(file_obj2) == checksum


def test_extract_filename():
    """Test filename extraction from path."""
    assert extract_filename('1/documents/test.pdf') == 'test.pdf'
    assert extract_filename('test.txt') == 'test.txt'
    assert extract_filename('1/folder/subfolder/file.doc') == 'file.doc'


def test_extract_folder_path():
    """Test folder path extraction."""
    path = '1/documents/reports/file.pdf'
    assert extract_folder_path(path) == '1/documents/reports'

    path2 = '1/file.txt'
    assert extract_folder_path(path2) == '1'


def test_validate_storage_path_valid(user):
    """Test storage path validation with valid path."""
    # Should not raise
    validate_storage_path(user.id, f'{user.id}/documents/test.pdf')


def test_validate_storage_path_wrong_user(user):
    """Test storage path validation with wrong user ID."""
    wrong_id = user.id + 100

    with pytest.raises(ValidationError, match='does not match owner'):
        validate_storage_path(
            user.id,
            f'{wrong_id}/documents/test.pdf',
        )


def test_validate_storage_path_no_user_id(user):
    """Test storage path validation without user ID."""
    with pytest.raises(ValidationError, match='must start with user ID'):
        validate_storage_path(user.id, 'documents/test.pdf')


def test_validate_storage_path_empty(user):
    """Test storage path validation with empty path."""
    with pytest.raises(ValidationError, match='cannot be empty'):
        validate_storage_path(user.id, '')


def test_get_file_extension():
    """Test file extension extraction."""
    assert get_file_extension('test.pdf') == 'pdf'
    assert get_file_extension('test.TXT') == 'txt'  # Lowercase
    assert get_file_extension('test') == ''  # No extension
    assert get_file_extension('test.tar.gz') == 'gz'  # Last extension
