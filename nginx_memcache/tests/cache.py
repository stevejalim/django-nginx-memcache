from django.http import HttpResponse
from django.test import TestCase
from django.test.client import RequestFactory
from django.conf import settings

from nginx_memcache.decorators import cache_page_nginx
from nginx_memcache.models import CachedPageRecord
from nginx_memcache.cache import (
    nginx_cache as cache,
    CACHE_ALIAS,
    get_cache_key,
    invalidate_from_request,
    bulk_invalidate
)


class CachedPageRecordTests(TestCase):

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
        return HttpResponse('content')

    # CACHE RECORD CREATION TESTS

    def test_lookup_record_created(self):
        # Basically the same as the default decorator test,
        # but with the class-level my_view
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 1)

    def test_lookup_record_not_created_if_disabled_in_settings(self):

        # Monkey-patch settings for test purposes
        setattr(settings, 'CACHE_NGINX_USE_LOOKUP_TABLE', False)

        factory = RequestFactory()
        # Clear the cache before we do anything.
        request = factory.get('/', SERVER_NAME="example1.com")
        cache.clear()
        cache_key = get_cache_key(request.get_host(), request.get_full_path())
        assert not cache.get(cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 0)

        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(request).content, 'content')

        assert cache.get(cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 0)

    def test_lookup_record_takes_hostname_by_default(self):
        # Cache the view, without expressing a lookup_identifier
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(
            CachedPageRecord.objects.get().parent_identifier,
            "example1.com"
        )

    def test_lookup_record_respects_varying_hostname_by_default(self):
        # this one needs a bit more set-up
        self.request = self.factory.get('/', SERVER_NAME="example2.com")
        cache.clear()
        self.cache_key = get_cache_key(
            self.request.get_host(),
            self.request.get_full_path()
        )
        assert not cache.get(self.cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 0)

        # and on with the test
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')
        assert cache.get(self.cache_key)

        self.assertEqual(
            CachedPageRecord.objects.get().parent_identifier,
            "example2.com"
        )

    def test_lookup_record_respects_explicit_identifier_arg(self):
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="foobarbaz"
        )
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(
            CachedPageRecord.objects.get().parent_identifier,
            "foobarbaz"
        )

    def test_lookup_record_respects_just_supplementary_identifier_arg(self):
        my_view_cached = cache_page_nginx(
            self.my_view,
            supplementary_identifier="bambashbop"
        )
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(
            CachedPageRecord.objects.get().supplementary_identifier,
            "bambashbop"
        )

    def test_lookup_record_respects_explicit_and_supp_identifiers(self):
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="foobarbaz",
            supplementary_identifier="bambashbop"
        )
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(
            CachedPageRecord.objects.get().parent_identifier,
            "foobarbaz"
        )
        self.assertEqual(
            CachedPageRecord.objects.get().supplementary_identifier,
            "bambashbop"
        )

    def test_multiple_lookup_records_for_different_keys_coexist(self):
        # We can fake this by cacheing the same HTTPResponse for two
        # different domains or lookup identifiers. Let's do it with
        # domains

        # First time, use example.com set in the setUp method
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 1)

        # Now do this for a different domain, without clearing
        # the cache, of course. This one needs a bit more set-up

        other_request = self.factory.get('/', SERVER_NAME="example2.com")
        other_cache_key = get_cache_key(
            other_request.get_host(),
            other_request.get_full_path()
        )

        # and on with the test
        my_view_cached = cache_page_nginx(self.my_view)

        self.assertEqual(my_view_cached(other_request).content, 'content')
        assert cache.get(other_cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 2)
        try:
            CachedPageRecord.objects.get(parent_identifier="example1.com")
            CachedPageRecord.objects.get(parent_identifier="example2.com")
        except CachedPageRecord.DoesNotExist, e:
            self.fail(e)

    def test_multiple_lookup_records_are_not_made_for_same_keys(self):
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 1)

        # And repeat, which should not another record
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')
        self.assertEqual(CachedPageRecord.objects.count(), 1)

        # BUT cache some content with a non-default lookup identifier
        # which HAS to be on a different domain else the test will fail for
        # creating a non-realistic situation where we try to use the same
        # same key for two pages, because the key is based on hostname + path,
        # and has no knowledge of the lookup_identifier that may be associated
        # with it.

        other_request = self.factory.get('/', SERVER_NAME="example2.com")
        other_cache_key = get_cache_key(
            other_request.get_host(),
            other_request.get_full_path()
        )

        # and on with the test
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="foobarbaz",
        )
        self.assertEqual(my_view_cached(other_request).content, 'content')
        assert cache.get(other_cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 2)

        # And, again, repeat. Again.
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="foobarbaz",
        )
        self.assertEqual(my_view_cached(self.request).content, 'content')

        self.assertEqual(CachedPageRecord.objects.count(), 2)

    # INVALIDATION TESTS

    def test_cache_invalidation_from_request(self):
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)
        self.assertEqual(CachedPageRecord.objects.count(), 1)

        # now invalidate the cache, using the supplied function call
        invalidate_from_request(self.request)

        self.assertEqual(
            cache.get(self.cache_key),
            None
        )
        # But, at least for this release, the CachedPageRecord is still present
        self.assertEqual(CachedPageRecord.objects.count(), 1)

    def test_cache_bulk_invalidation_via_identifier(self):

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
        assert cache.get(request_1_cache_key)

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
        assert cache.get(request_2_cache_key)

        # And a repeated path, but with a different identifier
        # (and on a separate domain, for test realism)
        request_3 = self.factory.get('/foo/', SERVER_NAME="example2.com")
        request_3_cache_key = get_cache_key(
            request_3.get_host(),
            request_3.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="test2"
        )
        self.assertEqual(my_view_cached(request_3).content, 'content')
        assert cache.get(request_3_cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # now invalidate based on the test1 identifier
        bulk_invalidate('test1')
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertEqual(cache.get(request_2_cache_key), None)
        self.assertNotEqual(cache.get(request_3_cache_key), None)
        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # now invalidate based on the test2 identifier
        bulk_invalidate('test2')
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertEqual(cache.get(request_2_cache_key), None)
        self.assertEqual(cache.get(request_3_cache_key), None)

        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

    def test_cache_bulk_invalidation_via_hostname_known_to_be_identifier(self):
        # V similar to above, but proving that the same thing applies
        # if you don't set a lookup_identifier and make do with the
        # default of the hostname as the identifier

        request_1 = self.factory.get('/foo/', SERVER_NAME="example1.com")
        request_1_cache_key = get_cache_key(
            request_1.get_host(),
            request_1.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
        )
        self.assertEqual(my_view_cached(request_1).content, 'content')
        assert cache.get(request_1_cache_key)

        request_2 = self.factory.get('/bar/', SERVER_NAME="example1.com")
        request_2_cache_key = get_cache_key(
            request_2.get_host(),
            request_2.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
        )
        self.assertEqual(my_view_cached(request_2).content, 'content')
        assert cache.get(request_2_cache_key)

        # And a repeated path, but with a different identifier
        # (and on a separate domain, for test realism)
        request_3 = self.factory.get('/foo/', SERVER_NAME="example2.com")
        request_3_cache_key = get_cache_key(
            request_3.get_host(),
            request_3.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
        )
        self.assertEqual(my_view_cached(request_3).content, 'content')
        assert cache.get(request_3_cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # now invalidate based on the example1.com host/identifier
        bulk_invalidate('example1.com')
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertEqual(cache.get(request_2_cache_key), None)
        self.assertNotEqual(cache.get(request_3_cache_key), None)
        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # now invalidate based on the example2.com host/identifier
        bulk_invalidate('example2.com')
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertEqual(cache.get(request_2_cache_key), None)
        self.assertEqual(cache.get(request_3_cache_key), None)

        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

    def test_cache_bulk_subset_invalidation_via_supplementary_identifier(self):

        # Put three pages into the cache, using the same view,
        # but 1 + 2 supplementary identifiers.

        request_1 = self.factory.get('/foo/', SERVER_NAME="example1.com")
        request_1_cache_key = get_cache_key(
            request_1.get_host(),
            request_1.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="testsite",
            supplementary_identifier="category-1"
        )
        self.assertEqual(my_view_cached(request_1).content, 'content')
        assert cache.get(request_1_cache_key)

        request_2 = self.factory.get('/bar/', SERVER_NAME="example1.com")
        request_2_cache_key = get_cache_key(
            request_2.get_host(),
            request_2.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="testsite",
            supplementary_identifier="category-2"
        )
        self.assertEqual(my_view_cached(request_2).content, 'content')
        assert cache.get(request_2_cache_key)

        request_3 = self.factory.get('/baz/', SERVER_NAME="example1.com")
        request_3_cache_key = get_cache_key(
            request_3.get_host(),
            request_3.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="testsite",
            supplementary_identifier="category-2"  # repeated identifier
        )
        self.assertEqual(my_view_cached(request_3).content, 'content')
        assert cache.get(request_3_cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # show that invalidating on a bogux main identifier does nothing
        bulk_invalidate('demosite')
        self.assertNotEqual(cache.get(request_1_cache_key), None)
        self.assertNotEqual(cache.get(request_2_cache_key), None)
        self.assertNotEqual(cache.get(request_3_cache_key), None)

        # now invalidate based on the category-1 supp. identifier
        bulk_invalidate('testsite', supplementary_identifier="category-1")
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertNotEqual(cache.get(request_2_cache_key), None)
        self.assertNotEqual(cache.get(request_3_cache_key), None)
        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # now invalidate based on the category-2 supp. identifier
        bulk_invalidate('testsite', supplementary_identifier="category-2")
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertEqual(cache.get(request_2_cache_key), None)
        self.assertEqual(cache.get(request_3_cache_key), None)

        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

    def test_cache_bulk_invalidation_via_identifier_only_is_paramount(self):
        # ie, if there is a supplementary identifier, a page will still
        # get zapped if the main lookup_identifier is invoked

        # Put three pages into the cache, using the same view,
        # but 1 + 2 supplementary identifiers.
        request_1 = self.factory.get('/foo/', SERVER_NAME="example1.com")
        request_1_cache_key = get_cache_key(
            request_1.get_host(),
            request_1.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="testsite",
            supplementary_identifier="category-1"
        )
        self.assertEqual(my_view_cached(request_1).content, 'content')
        assert cache.get(request_1_cache_key)

        request_2 = self.factory.get('/bar/', SERVER_NAME="example1.com")
        request_2_cache_key = get_cache_key(
            request_2.get_host(),
            request_2.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="testsite",
            supplementary_identifier="category-2"
        )
        self.assertEqual(my_view_cached(request_2).content, 'content')
        assert cache.get(request_2_cache_key)

        request_3 = self.factory.get('/baz/', SERVER_NAME="example1.com")
        request_3_cache_key = get_cache_key(
            request_3.get_host(),
            request_3.get_full_path()
        )
        my_view_cached = cache_page_nginx(
            self.my_view,
            lookup_identifier="testsite",
            supplementary_identifier="category-2"  # repeated identifier
        )
        self.assertEqual(my_view_cached(request_3).content, 'content')
        assert cache.get(request_3_cache_key)

        self.assertEqual(CachedPageRecord.objects.count(), 3)

        # show that invalidating on a bogus lookup identifier does nothing
        bulk_invalidate('demosite')
        self.assertNotEqual(cache.get(request_1_cache_key), None)
        self.assertNotEqual(cache.get(request_2_cache_key), None)
        self.assertNotEqual(cache.get(request_3_cache_key), None)

        # now invalidate based on the real lookup identifier
        bulk_invalidate('testsite')
        self.assertEqual(cache.get(request_1_cache_key), None)
        self.assertEqual(cache.get(request_2_cache_key), None)
        self.assertEqual(cache.get(request_3_cache_key), None)
        # we should still have those three records present in the DB
        self.assertEqual(CachedPageRecord.objects.count(), 3)

    # MODEL METHOD TESTS
    # Could go into their own models.py test module, of course

    def test_memcached_key_property_on_lookup(self):
        # Cache the view, without expressing a lookup_identifier
        my_view_cached = cache_page_nginx(self.my_view)
        self.assertEqual(my_view_cached(self.request).content, 'content')

        assert cache.get(self.cache_key)

        cpr = CachedPageRecord.objects.get()

        expected_memcached_key = "%s:%s:%s" % (
            settings.CACHES[CACHE_ALIAS].get('KEY_PREFIX'),
            1,
            cpr.base_cache_key
        )

        self.assertEqual(
            cpr.memcached_key,
            expected_memcached_key
        )
