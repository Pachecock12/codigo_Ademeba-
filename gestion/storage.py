from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class SupabaseS3Storage(S3Boto3Storage):
    def url(self, name, parameters=None, expire=None):
        try:
            if not getattr(settings, 'AWS_S3_ENDPOINT_URL', None):
                return name
            clean_name = name.lstrip('/')
            project_id = settings.AWS_S3_ENDPOINT_URL.replace('https://', '').split('.')[0]
            return f'https://{project_id}.supabase.co/storage/v1/object/public/{settings.AWS_STORAGE_BUCKET_NAME}/{clean_name}'
        except Exception:
            return name
