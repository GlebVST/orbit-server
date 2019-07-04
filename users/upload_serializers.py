from __future__ import unicode_literals
import io
from hashids import Hashids
import os
import hashlib
import logging
import mimetypes
from PIL import Image
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import serializers
from common.viewutils import newUuid, md5_uploaded_file
from .models import *

logger = logging.getLogger('gen.usrl')

class UploadDocumentSerializer(serializers.Serializer):
    document = serializers.FileField(max_length=None, allow_empty_file=False)
    fileMd5 = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=255, required=False)
    image_h = serializers.IntegerField(min_value=0, required=False)
    image_w = serializers.IntegerField(min_value=0, required=False)
    is_certificate = serializers.BooleanField()

    class Meta:
        fields = (
            'document',
            'fileMd5',
            'name',
            'image_h',
            'image_w',
            'is_certificate'
        )

    def validate(self, data):
        """
        Validate the client file_md5 matches server file_md5
        """
        if 'document' in data and 'fileMd5' in data:
            client_md5 = data['fileMd5']
            server_md5 = md5_uploaded_file(data['document'])
            if client_md5 != server_md5:
                raise serializers.ValidationError('Check md5sum failed')
        return data

    def create(self, validated_data):
        """Create Document instance.
        It expects that View has passed the following keys to the serializer.save
        method, which then appear in validated_data:
            user: User instance
        """
        hashgen = Hashids(salt=settings.DOCUMENT_HASHIDS_SALT, min_length=10)
        newDoc = validated_data['document'] # UploadedFile (or subclass)
        fileName = validated_data.get('name', '')
        #logger.debug('uploaded filename: {0}'.format(fileName)) # this raised UnicodeError for unicode filenames
        basename, fileExt = os.path.splitext(fileName)
        fileMd5 = validated_data['fileMd5']
        docName = fileMd5 + fileExt
        image_h=validated_data.get('image_h', None)
        image_w=validated_data.get('image_w', None)
        set_id = ''
        thumb_size = 200
        thumbMd5 = None
        is_image = newDoc.content_type.lower().startswith('image')
        if is_image:
            try:
                im = Image.open(newDoc)
                image_w, image_h = im.size
                if image_w > thumb_size or image_h > thumb_size:
                    im.thumbnail((thumb_size, thumb_size), Image.ANTIALIAS)
                    mime = mimetypes.guess_type(fileName)
                    plain_ext = mime[0].split('/')[1]
                    memory_file = io.BytesIO()
                    # save thumb to memory_file
                    im.save(memory_file, plain_ext, quality=90)
                    # calculate md5sum of thumb
                    thumbMd5 = hashlib.md5(memory_file.getvalue()).hexdigest()
            except IOError as e:
                logger.exception('UploadDocument: Image open failed.')
            else:
                set_id = newUuid()
        instance = Document(
            md5sum = fileMd5,
            content_type = newDoc.content_type,
            name=validated_data.get('name', ''),
            image_h=image_h,
            image_w=image_w,
            set_id=set_id,
            user=validated_data.get('user'),
            is_certificate=validated_data.get('is_certificate')
        )
        # Save the file, and save the model instance
        instance.document.save(docName.lower(), newDoc, save=True)
        instance.referenceId = 'document' + hashgen.encode(instance.pk)
        instance.save(update_fields=('referenceId',))
        # Save thumbnail instance
        if thumbMd5:
            thumbName = thumbMd5 + fileExt
            thumb_instance = Document(
                md5sum = thumbMd5,
                content_type = newDoc.content_type,
                name=instance.name,
                image_h=thumb_size,
                image_w=thumb_size,
                set_id=set_id,
                is_thumb=True,
                user=validated_data.get('user'),
                is_certificate=validated_data.get('is_certificate')
            )
            # Save the thumb file, and save the model instance
            memory_file.seek(0)
            cf = ContentFile(memory_file.getvalue()) # Create a ContentFile from the memory_file
            thumb_instance.document.save(thumbName.lower(), cf, save=True)
            thumb_instance.referenceId = 'document' + hashgen.encode(thumb_instance.pk)
            thumb_instance.save(update_fields=('referenceId',))
        return instance

class UploadRosterFileSerializer(serializers.Serializer):
    document = serializers.FileField(max_length=None, allow_empty_file=False)
    name = serializers.CharField(max_length=255, required=False)

    class Meta:
        fields = (
            'document',
            'name',
        )

    def create(self, validated_data):
        """Create OrgFile instance for file_type=NEW_PROVIDER.
        Extra keys expected in validated_data:
            user: User instance
            organization: Organization instance
        """
        user = validated_data['user']
        org = validated_data['organization']
        newDoc = validated_data['document'] # UploadedFile (or subclass)
        now = timezone.now()
        fileName = validated_data.get('name', '')
        defaultFileName = 'upload_roster_{0:%Y%m%d%H%M%S}.csv'.format(now)
        if not fileName:
            fileName = defaultFileName
        try:
            logger.debug('UploadRosterFile filename: {0}'.format(fileName))
        except UnicodeDecodeError:
            fileName = defaultFileName
        instance = OrgFile.objects.create(
                user=user,
                organization=org,
                document=newDoc,
                name=fileName,
                file_type=OrgFile.NEW_PROVIDER,
                content_type=newDoc.content_type
            )
        return instance
