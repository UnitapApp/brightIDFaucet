"""
Contains all the fields related classes to support custom features
such as variants in Cloudflare Images
"""

from django.db.models.base import Model
from django.db.models.fields.files import (
    FileField,
    ImageFieldFile,
    ImageField,
    ImageFileDescriptor,
)
from .storages import CloudflareImagesStorage
from django.conf import settings

class CloudflareImagesFileDescriptor(ImageFileDescriptor):
    """
    Inherits ImageField's descriptor class
    """

    pass


class CloudflareImagesFieldFile(ImageFieldFile):
    """
    Inherits ImageField's attr class
    """
    def __init__(self, instance: Model, field: FileField, name: str | None) -> None:
        super().__init__(instance, field, name)

        self.storage = CloudflareImagesStorage()

    @property
    def url(self):
        """
        Overriding the default url method to pass our variant
        """
        return self.storage.url_with_variant(self.name, variant=self.field.variant)


class CloudflareImagesField(ImageField):
    """
    Custom field based on ImageField allowing us to pass a variant
    """

    attr_class = CloudflareImagesFieldFile
    descriptor_class = CloudflareImagesFileDescriptor
    description = "Image"
    storage = CloudflareImagesStorage

    def __init__(
        self,
        verbose_name=None,
        name=None,
        width_field=None,
        height_field=None,
        variant=None,
        **kwargs,
    ):
        """
        Calling ImageFieldFile constructor and setting our variant
        """
        self.variant = variant or "public"
        super().__init__(verbose_name, name, width_field, height_field, **kwargs)

    def deconstruct(self):
        """
        Returns the deconstructed version of our field.
        Same as ImageField with variant on top
        """
        name, path, args, kwargs = super().deconstruct()
        kwargs["variant"] = self.variant
        return name, path, args, kwargs