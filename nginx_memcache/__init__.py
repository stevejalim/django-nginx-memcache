VERSION = (0, 2, 4,)


def get_version():
    version = '%s.%s.%s' % (
        VERSION[0],
        VERSION[1],
        VERSION[2]
    )
    try:
        version = '%s.%s.%s %s' % (
            VERSION[0],
            VERSION[1],
            VERSION[2],
            VERSION[3]
        )
    except IndexError:
        pass
    return version

# Ensure you have the following import in your main Django app

# from nginx_memcache.signals import (
#     handle_single_page_invalidation,
#     handle_multiple_page_invalidation
# )
