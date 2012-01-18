from django.conf import settings
from django.db import models


class CachedPageRecord(models.Model):
    """When a page is cached, the user has the option (via the decorator) to
    note this in a DB-backed lookup table. This data is stored in this model.

    Note that you'll ideally be using a database implementation
    that can enforce UNIQUE constraints.

    The most interesting use of this model is cache.bulk_invalidate() function.
    Read its docstring for more info.

    """

    # NB: because the base_cache_key is the primary key,
    # there is no 'id' field on this model
    base_cache_key = models.CharField(
        max_length=32,  # standard output of hexdigest() on an md5
        primary_key=True,  # which implies unique=True
        help_text=(
            "The md5 based on the host and path. This will be " +
            "combined with any prefix and the version to get the " +
            "real cache key stored in memcache"
        )
    )

    parent_identifier = models.CharField(
        blank=False,
        null=False,
        max_length=255,
        db_index=True,
        help_text=(
            "An identifier for whatever your parent object is." +
            "Could be a slug, a subdomain, or a Site ID [as a string]. " +
            "If no lookup_identifier is passed to the cache decorator, " +
            "this value will be the hostname of the server (which is fine)."
        )
    )

    supplementary_identifier = models.CharField(
        blank=True,
        null=True,
        max_length=255,
        help_text=(
            "Additional meta string you can use to scope your invalidation " +
            "calls to a subset of keys - eg 'news' or 'category_3'"
        )
    )

    class Meta:
        unique_together = (
            (
                'parent_identifier',
                'base_cache_key',
                'supplementary_identifier'
            ),
        )

    def __unicode__(self):
        return "%s/%s/%s" % (
            self.base_cache_key,
            self.parent_identifier,
            self.supplementary_identifier
        )

    @property
    def memcached_key(self):
        """
        Complete representation of the cache key used by memcache.
        Includes the appropriate Djagno prefix and version.

        """

        CACHE_ALIAS = getattr(settings, 'CACHE_NGINX_ALIAS', 'default')
        return "%s:%s:%s" % (
            settings.CACHES[CACHE_ALIAS].get('KEY_PREFIX'),
            1,  # CACHE_VERSION defaults to 1 and nginx only ever seeks that
            self.base_cache_key
        )
