from django.contrib import admin

from nginx_memcache.models import CachedPageRecord


class CachedPageRecordAdmin(admin.ModelAdmin):
    _all_fields = [
        'base_cache_key',
        'parent_identifier',
        'supplementary_identifier'
    ]
    list_display = _all_fields[:]
    search_fields = _all_fields[:]
    readonly_fields = _all_fields[:]

admin.site.register(CachedPageRecord, CachedPageRecordAdmin)
