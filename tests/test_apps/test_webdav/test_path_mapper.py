"""Tests for WebDAV path mapper."""

import pytest

from server.apps.webdav.path_mapper import PathMapper


class TestPathMapperToStoragePath:
    """Tests for to_storage_path method."""

    def test_root_path(self):
        """Test converting root path to storage path."""
        mapper = PathMapper(user_id=123)

        assert mapper.to_storage_path('/') == '123'
        assert mapper.to_storage_path('') == '123'

    def test_simple_file(self):
        """Test converting simple file path."""
        mapper = PathMapper(user_id=123)

        assert mapper.to_storage_path('/file.txt') == '123/file.txt'

    def test_nested_path(self):
        """Test converting nested path."""
        mapper = PathMapper(user_id=123)

        result = mapper.to_storage_path('/documents/reports/file.pdf')
        assert result == '123/documents/reports/file.pdf'

    def test_strips_leading_slashes(self):
        """Test that leading slashes are normalized."""
        mapper = PathMapper(user_id=123)

        assert mapper.to_storage_path('///file.txt') == '123/file.txt'

    def test_strips_trailing_slashes(self):
        """Test that trailing slashes are normalized."""
        mapper = PathMapper(user_id=123)

        assert mapper.to_storage_path('/folder/') == '123/folder'


class TestPathMapperToWebdavPath:
    """Tests for to_webdav_path method."""

    def test_root_path(self):
        """Test converting user root to WebDAV root."""
        mapper = PathMapper(user_id=123)

        assert mapper.to_webdav_path('123') == '/'

    def test_simple_file(self):
        """Test converting simple storage path."""
        mapper = PathMapper(user_id=123)

        assert mapper.to_webdav_path('123/file.txt') == '/file.txt'

    def test_nested_path(self):
        """Test converting nested storage path."""
        mapper = PathMapper(user_id=123)

        result = mapper.to_webdav_path('123/documents/reports/file.pdf')
        assert result == '/documents/reports/file.pdf'

    def test_wrong_user_path(self):
        """Test converting path that doesn't match user ID."""
        mapper = PathMapper(user_id=123)

        # Should still return a path but without stripping prefix
        result = mapper.to_webdav_path('456/file.txt')
        assert result == '/456/file.txt'


class TestPathMapperHelpers:
    """Tests for helper methods."""

    def test_get_parent_path_root(self):
        """Test getting parent of root-level item."""
        mapper = PathMapper(user_id=123)

        assert mapper.get_parent_path('/file.txt') == '/'
        assert mapper.get_parent_path('/folder') == '/'

    def test_get_parent_path_nested(self):
        """Test getting parent of nested item."""
        mapper = PathMapper(user_id=123)

        assert mapper.get_parent_path('/documents/file.txt') == '/documents'
        result = mapper.get_parent_path('/documents/reports/file.pdf')
        assert result == '/documents/reports'

    def test_get_parent_path_root_itself(self):
        """Test getting parent of root path."""
        mapper = PathMapper(user_id=123)

        assert mapper.get_parent_path('/') == '/'
        assert mapper.get_parent_path('') == '/'

    def test_get_name_file(self):
        """Test extracting filename."""
        mapper = PathMapper(user_id=123)

        assert mapper.get_name('/file.txt') == 'file.txt'
        assert mapper.get_name('/documents/report.pdf') == 'report.pdf'

    def test_get_name_folder(self):
        """Test extracting folder name."""
        mapper = PathMapper(user_id=123)

        assert mapper.get_name('/documents') == 'documents'

    def test_get_name_root(self):
        """Test getting name of root path."""
        mapper = PathMapper(user_id=123)

        assert mapper.get_name('/') == ''
        assert mapper.get_name('') == ''

    def test_join_paths(self):
        """Test joining parent path and name."""
        mapper = PathMapper(user_id=123)

        assert mapper.join_paths('/', 'file.txt') == '/file.txt'
        assert mapper.join_paths('/documents', 'file.txt') == '/documents/file.txt'

    def test_is_root(self):
        """Test root path detection."""
        mapper = PathMapper(user_id=123)

        assert mapper.is_root('/') is True
        assert mapper.is_root('') is True
        assert mapper.is_root('/documents') is False

    def test_user_id_property(self):
        """Test user_id property."""
        mapper = PathMapper(user_id=123)

        assert mapper.user_id == 123


class TestPathMapperValidation:
    """Tests for path validation."""

    def test_validate_normal_path(self):
        """Test validation of normal paths."""
        mapper = PathMapper(user_id=123)

        assert mapper.validate_path('/file.txt') is True
        assert mapper.validate_path('/documents/report.pdf') is True

    def test_validate_rejects_path_traversal(self):
        """Test that path traversal is rejected."""
        mapper = PathMapper(user_id=123)

        assert mapper.validate_path('/..') is False
        assert mapper.validate_path('/../etc/passwd') is False
        assert mapper.validate_path('/documents/../../../etc/passwd') is False

    def test_validate_rejects_null_bytes(self):
        """Test that null bytes are rejected."""
        mapper = PathMapper(user_id=123)

        assert mapper.validate_path('/file\x00.txt') is False
