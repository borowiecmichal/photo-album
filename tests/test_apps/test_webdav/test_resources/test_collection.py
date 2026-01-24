"""Tests for WebDAV folder collection."""

import pytest

from server.apps.files.models import File
from server.apps.webdav.path_mapper import PathMapper
from server.apps.webdav.resources.collection import FolderCollection
from server.apps.webdav.resources.file_resource import (
    FileResource,
    NewFileResource,
)


class TestFolderCollection:
    """Tests for FolderCollection."""

    @pytest.mark.django_db
    def test_get_creation_date(self, user, webdav_environ, path_mapper):
        """Test getting creation date (fixed for implicit folders)."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        assert collection.get_creation_date() == 0.0

    @pytest.mark.django_db
    def test_get_last_modified_empty(self, user, webdav_environ, path_mapper):
        """Test last modified for empty folder."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        # Should return current time for empty folder
        last_modified = collection.get_last_modified()
        assert last_modified > 0

    @pytest.mark.django_db
    def test_get_last_modified_with_files(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
        mock_s3,
    ):
        """Test last modified based on files in folder."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        last_modified = collection.get_last_modified()

        assert last_modified == sample_file.modified_at.timestamp()

    @pytest.mark.django_db
    def test_get_member_names_root(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
    ):
        """Test listing root directory members."""
        # Create files in root and subdirectory
        File.objects.create(
            user=user,
            file='{id}/file1.txt'.format(id=user.id),
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        File.objects.create(
            user=user,
            file='{id}/documents/file2.txt'.format(id=user.id),
            size_bytes=200,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )

        collection = FolderCollection('/', webdav_environ, user, path_mapper)

        members = collection.get_member_names()

        # Should have file1.txt and documents folder
        assert sorted(members) == ['documents', 'file1.txt']

    @pytest.mark.django_db
    def test_get_member_names_subfolder(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
    ):
        """Test listing subfolder members."""
        # Create files in documents and its subdirectory
        File.objects.create(
            user=user,
            file='{id}/documents/file1.txt'.format(id=user.id),
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        File.objects.create(
            user=user,
            file='{id}/documents/reports/file2.txt'.format(id=user.id),
            size_bytes=200,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )

        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        members = collection.get_member_names()

        assert sorted(members) == ['file1.txt', 'reports']

    @pytest.mark.django_db
    def test_get_member_file(
        self,
        user,
        webdav_environ,
        sample_file,
        path_mapper,
        mock_s3,
    ):
        """Test getting file member."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        member = collection.get_member('test.txt')

        assert isinstance(member, FileResource)

    @pytest.mark.django_db
    def test_get_member_folder(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
    ):
        """Test getting folder member."""
        # Create file in subfolder
        File.objects.create(
            user=user,
            file='{id}/documents/reports/file.txt'.format(id=user.id),
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        member = collection.get_member('reports')

        assert isinstance(member, FolderCollection)

    @pytest.mark.django_db
    def test_get_member_not_found(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
    ):
        """Test getting nonexistent member."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        with pytest.raises(ValueError):
            collection.get_member('nonexistent.txt')

    @pytest.mark.django_db
    def test_create_empty_resource(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test creating placeholder for new file."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        resource = collection.create_empty_resource('newfile.txt')

        assert isinstance(resource, NewFileResource)
        assert resource.path == '/documents/newfile.txt'

    @pytest.mark.django_db
    def test_create_collection(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test creating subfolder (implicit)."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        subfolder = collection.create_collection('newfolder')

        assert isinstance(subfolder, FolderCollection)
        assert subfolder.path == '/documents/newfolder'

    @pytest.mark.django_db
    def test_delete_folder(
        self,
        user,
        webdav_environ,
        path_mapper,
        mock_s3,
    ):
        """Test deleting folder and contents."""
        # Create files in folder
        storage_path1 = '{id}/documents/file1.txt'.format(id=user.id)
        storage_path2 = '{id}/documents/sub/file2.txt'.format(id=user.id)

        mock_s3.Bucket('photo-album').put_object(
            Key=storage_path1,
            Body=b'content1',
        )
        mock_s3.Bucket('photo-album').put_object(
            Key=storage_path2,
            Body=b'content2',
        )

        File.objects.create(
            user=user,
            file=storage_path1,
            size_bytes=8,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )
        File.objects.create(
            user=user,
            file=storage_path2,
            size_bytes=8,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )

        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        collection.delete()

        # All files should be deleted
        assert File.objects.filter(user=user).count() == 0

    @pytest.mark.django_db
    def test_support_recursive_delete(
        self,
        user,
        webdav_environ,
        path_mapper,
    ):
        """Test recursive delete support."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        assert collection.support_recursive_delete() is True

    @pytest.mark.django_db
    def test_get_etag(self, user, webdav_environ, path_mapper):
        """Test that folders don't have ETags."""
        collection = FolderCollection(
            '/documents',
            webdav_environ,
            user,
            path_mapper,
        )

        assert collection.get_etag() is None


class TestFolderCollectionUserIsolation:
    """Tests for user isolation in folder collection."""

    @pytest.mark.django_db
    def test_get_member_names_only_own_files(
        self,
        user,
        other_user,
        webdav_environ,
        path_mapper,
        mock_s3,
    ):
        """Test that only user's files are listed."""
        # Create file for first user
        File.objects.create(
            user=user,
            file='{id}/myfile.txt'.format(id=user.id),
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='a' * 64,
        )

        # Create file for other user
        File.objects.create(
            user=other_user,
            file='{id}/otherfile.txt'.format(id=other_user.id),
            size_bytes=100,
            mime_type='text/plain',
            checksum_sha256='b' * 64,
        )

        collection = FolderCollection('/', webdav_environ, user, path_mapper)

        members = collection.get_member_names()

        # Should only see first user's file
        assert members == ['myfile.txt']
