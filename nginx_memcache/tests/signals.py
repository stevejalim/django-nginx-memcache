"""Feature-level tests to confirm that
the signal handlers are work
"""

from django.http import HttpResponse
from django.test import TestCase
from django.test.client import RequestFactory
from django.conf import settings

from nginx_memcache.decorators import cache_page_nginx
from nginx_memcache.models import CachedPageRecord
from nginx_memcache.cache import (
    nginx_cache as cache,
    get_cache_key,
    CACHE_NGINX_DEFAULT_COOKIE
)
from nginx_memcache.signals import (
    invalidate_single_page,
    invalidate_many_pages
)


class CacheSignalTests(TestCase):

    def setUp(self):
        #monkey-patch settings for test purposes
        setattr(settings, 'CACHE_NGINX_USE_LOOKUP_TABLE', True)

        self.factory = RequestFactory()
        # Clear the cache before we do anything.
        self.request = self.factory.get('/', SERVER_NAME="example1.com")
        cache.clear()
        self.cache_key = get_cache_key(
            self.request.get_host(),
            self.request.get_full_path()
        )
        assert not cache.get(self.cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 0)

    def my_view(self, request):
        """Class-wide test view"""
        return HttpResponse('content')

    def test_invalidate_single_page(self):

        # Cache a page
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        # Confirm in cache
        assert cache.get(self.cache_key)

        # invalidate the cache via the signal
        invalidate_single_page.send_robust(
            sender=None,  # Not relevant in our handler code
            request_host=u"example1.com",
            request_path=u"/",
            page_version='',
            cookie_name=CACHE_NGINX_DEFAULT_COOKIE
        )
        # confirm no longer in cache
        assert not cache.get(self.cache_key)

    def test_invalidate_single_page_using_minimal_args(self):
        # Also confirm that invalidation doesn't need
        # page_version or cookie_name kwargs

        # Cache a page
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        # Confirm in cache
        assert cache.get(self.cache_key)

        # invalidate the cache via the signal
        invalidate_single_page.send_robust(
            sender=None,  # Not relevant in our handler code
            request_host=u"example1.com",
            request_path=u"/",
        )
        # confirm no longer in cache
        assert not cache.get(self.cache_key)

    def test_invalidate_many_pages(self):

        # 1. Cache two pages with the same lookup_identifier

        # Put two pages into the cache, using the same view, but two separate
        # paths, so they count as separate pages

        request_1 = self.factory.get('/foo/', SERVER_NAME="example1.com")
        request_1_cache_key = get_cache_key(
            request_1.get_host(),
            request_1.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="test1"
        )
        self.assertEqual(my_view_cached(request_1).content, 'content')

        request_2 = self.factory.get('/bar/', SERVER_NAME="example1.com")
        request_2_cache_key = get_cache_key(
            request_2.get_host(),
            request_2.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="test1"
        )
        self.assertEqual(my_view_cached(request_2).content, 'content')

        # 2. Cache two pages with a different lookup_identifier
        #    from above, but unique supplementary_identifiers

        request_3 = self.factory.get('/moo/', SERVER_NAME="example1.com")
        request_3_cache_key = get_cache_key(
            request_3.get_host(),
            request_3.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="test2",
            supplementary_identifier="AAA"
        )
        self.assertEqual(my_view_cached(request_3).content, 'content')

        request_4 = self.factory.get('/boo/', SERVER_NAME="example1.com")
        request_4_cache_key = get_cache_key(
            request_4.get_host(),
            request_4.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="test2",
            supplementary_identifier="BBB"
        )
        self.assertEqual(my_view_cached(request_4).content, 'content')

        # 3. Confirm all in cache and that keys are unique

        assert cache.get(request_1_cache_key)
        assert cache.get(request_2_cache_key)
        assert cache.get(request_3_cache_key)
        assert cache.get(request_4_cache_key)

        self.assert_(
            request_1_cache_key != request_2_cache_key != \
            request_3_cache_key != request_4_cache_key
        )

        # 4. Invalidate first lookup_identifier via the signal
        invalidate_many_pages.send_robust(
            sender=None,  # Not needed
            lookup_identifier="test1"
        )

        # 5. Confirm those two pages no longer in cache, but
        #    the others are
        assert not cache.get(request_1_cache_key)
        assert not cache.get(request_2_cache_key)
        assert cache.get(request_3_cache_key)
        assert cache.get(request_4_cache_key)

        # 6. Invalidate using the second
        #    lookup_identifier + first supplementary_identifier
        #    via the signal
        invalidate_many_pages.send_robust(
            sender=None,  # Not needed
            lookup_identifier="test2",
            supplementary_identifier="AAA"
        )

        # 7. Confirm that single page no longer in cache
        assert not cache.get(request_1_cache_key)
        assert not cache.get(request_2_cache_key)
        assert not cache.get(request_3_cache_key)
        assert cache.get(request_4_cache_key)

        # 8. invalidate using the second
        #    lookup_identifier as a blanket call

        invalidate_many_pages.send_robust(
            sender=None,  # Not needed
            lookup_identifier="test2"
        )

        # 9. confirm that the final page no longer in cache
        assert not cache.get(request_1_cache_key)
        assert not cache.get(request_2_cache_key)
        assert not cache.get(request_3_cache_key)
        assert not cache.get(request_4_cache_key)
