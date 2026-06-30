from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class SupabaseS3Storage(S3Boto3Storage):
    def url(self, name, parameters=None, expire=None):
        if not getattr(settings, 'AWS_S3_ENDPOINT_URL', None):
            return super().url(name, parameters, expire)
        name = self._normalize_name(self._clean_name(name))
        project_id = settings.AWS_S3_ENDPOINT_URL.replace('https://', '').split('.')[0]
        return f'https://{project_id}.supabase.co/storage/v1/object/public/{settings.AWS_STORAGE_BUCKET_NAME}/{name}'
