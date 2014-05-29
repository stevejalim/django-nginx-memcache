import logging

import hashlib

from django.conf import settings
from django.core.cache import get_cache
from django.db import IntegrityError
from django.template.response import TemplateResponse
from django.utils.encoding import DjangoUnicodeDecodeError
from django.utils.html import strip_spaces_between_tags as minify_html

from .models import CachedPageRecord

CACHE_NGINX_DEFAULT_COOKIE = getattr(settings, 'CACHE_NGINX_COOKIE', 'pv')
CACHE_TIME = getattr(settings, 'CACHE_NGINX_TIME', 3600 * 24)
CACHE_ALIAS = getattr(settings, 'CACHE_NGINX_ALIAS', 'default')
CACHE_MINIFY_HTML = getattr(settings, 'CACHE_MINIFY_HTML', False)
nginx_cache = get_cache(CACHE_ALIAS)


def cache_response(
        request,
        response,
        cache_timeout=CACHE_TIME,
        cookie_name=CACHE_NGINX_DEFAULT_COOKIE,
        page_version_fn=None,
        lookup_identifier=None,
        supplementary_identifier=None
    ):

    """Class based view responses TemplateResponse objects and do not call
    render automatically, you we must trigger this."""
    if type(response) is TemplateResponse and not response.is_rendered:
        response.render()

    """ Minify the HTML outout if set in settings. """
    if CACHE_MINIFY_HTML:
        if 'text/html' in response['Content-Type']:
            try:
                response.content = minify_html(response.content.strip())
            except DjangoUnicodeDecodeError:
                pass

    """Cache this response for the web server to grab next time."""
    # get page version
    if page_version_fn:
        pv = page_version_fn(request)
    else:
        pv = ''
    cache_key = get_cache_key(
        request_host=request.get_host(),
        request_path=request.get_full_path(),
        page_version=pv,
        cookie_name=cookie_name
    )
    logging.info("Cacheing %s %s %s %s with key %s" % (
        request.get_host(), request.get_full_path(), pv, cookie_name, cache_key)
    )

    nginx_cache.set(cache_key, response.content, cache_timeout)

    # Store the version, if any specified.
    if pv:
        response.set_cookie(cookie_name, pv)

    # Add record of cacheing taking place to
    # invalidation lookup table, if appropriate
    if getattr(settings, 'CACHE_NGINX_USE_LOOKUP_TABLE', False):
        if not lookup_identifier:
            # If no identifier specified, use the hostname.
            # If you prefer, you could pass in a Site.id, etc
            lookup_identifier = request.get_host()
        add_key_to_lookup(
            cache_key,
            lookup_identifier,
            supplementary_identifier
        )


def get_cache_key(
        request_host,
        request_path,
        page_version='',
        cookie_name=CACHE_NGINX_DEFAULT_COOKIE
    ):
    """ Use the request host, request path and
        optional page version to get cache key."""
    raw_key = u'%s%s&%s=%s' % (
        request_host,
        request_path,
        cookie_name,
        page_version
    )
    return hashlib.md5(raw_key).hexdigest()


def invalidate_from_request(
        request,
        page_version='',
        cookie_name=CACHE_NGINX_DEFAULT_COOKIE
    ):
    """Delete cache key for this request and page version."""
    invalidate(
        request_host=request.get_host(),
        request_path=request.get_full_path(),
        page_version=page_version,
        cookie_name=cookie_name
    )


def invalidate(
        request_host,
        request_path,
        page_version='',
        cookie_name=CACHE_NGINX_DEFAULT_COOKIE
    ):
    """Delete cache key for this request path and page version."""
    cache_key = get_cache_key(
        request_host=request_host,
        request_path=request_path,
        page_version=page_version,
        cookie_name=cookie_name
    )
    logging.info("Invaldidating key '%s'" % cache_key)

    nginx_cache.delete(cache_key)


def bulk_invalidate(
        lookup_identifier,
        supplementary_identifier=None
    ):
    """Find all the pages in the lookup table that are identifed by the args
    and invalidate the/any cache for them.

    Note that this does not invalidate by URI-derived key; it invalidates
    *all* URI-derived keys via the particular lookup_identifier (and an
    optional supplementary_identifier) they have been associated with.

    Unless explicitly set in the nginx_cache_page decorator, the
    lookup_identifier is the value of request.get_host()

    Examples: a page with Django-generated cache key of
    'aaabbaaabbbaabbababab2424242412' may be within a site foo.com.

    So, calling bulk_invalidate with the output of request.get_host() as
    the layout_identifier argument will cause any cached paged for that host
    to be invalidated.

    And if the page with a key of 'aaabbaaabbbaabbababab2424242412' was
    within a 'news' section of site, and links to it may appear on other
    'news' pages, but nowhere else in the site, you may have a use case where
    only 'news' pages really needed to be invalidated.

    So, provided that the supplementary_identifier arg 'news' was passed to the
    nginx_cache_page decorator in the first place, you can invalidate only the
    pages in that 'news' subset by passing the 'news' as the
    supplementary_identifier here.

    """

    relevant_records = CachedPageRecord.objects.filter(
        parent_identifier=lookup_identifier,
    )

    if supplementary_identifier:
        relevant_records = relevant_records.filter(
            supplementary_identifier=supplementary_identifier
        )

    keys_to_delete = [record.base_cache_key for record in relevant_records]
    logging.info("Bulk invalidation of these keys: %s" % str(keys_to_delete))

    nginx_cache.delete_many(keys_to_delete)

    # NB: we _don't_ delete the objects for the keys we've just invalidated -
    # there's little overhead in trying to invalidate an already-invalid key
    # in memcache, whereas dropping rows from the DB to replace them
    # potentially milliseconds later is a more significant hit.
    #
    # Yes, in the future, there will be some kind of cleanup, probably
    # introducing an expiry_datetime field on the model


def add_key_to_lookup(
        cache_key,
        lookup_identifier,
        supplementary_identifier
    ):
    """Adds a CachedPageRecord to the lookup table, ensuring no duplicates of
       this data are also stored.
    """

    cpr = CachedPageRecord(
        base_cache_key=cache_key,
        parent_identifier=lookup_identifier,
        supplementary_identifier=supplementary_identifier
    )
    try:
        cpr.save()
    except IntegrityError:
        # Because it already exists, and we only
        # ever need one entry per cached page
        pass


def remove_key_from_lookup(
        cache_key,
        lookup_identifier,
        supplementary_identifier
    ):
    """Not currently unit tested, but will cleanly remove a CachedPageRecord"""

    try:
        cpr = CachedPageRecord.objects.get(
            base_cache_key=cache_key,
            parent_identifier=lookup_identifier,
            supplementary_identifier=supplementary_identifier
        )
        cpr.delete()
    except CachedPageRecord.DoesNotExist:
        pass
