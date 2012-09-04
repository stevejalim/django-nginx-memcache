"""Custom signals and their handlers,
to make it easier to call the
invalidation functions
"""

from django.dispatch import Signal, receiver

from .cache import invalidate, bulk_invalidate

# Signals
invalidate_single_page = Signal(
    providing_args=[
        "request_host",
        "request_path",
        "page_version",
        "cookie_name"
    ]
)

invalidate_many_pages = Signal(
    providing_args=[
        "lookup_identifier",
        "supplementary_identifier",
    ]
)


# Handlers, connected to those signals

@receiver(invalidate_single_page)
def handle_single_page_invalidation(sender, signal, **provided_args):
    invalidate(**provided_args)  # Hand it on with just the core things in there


@receiver(invalidate_many_pages)
def handle_multiple_page_invalidation(sender, signal, **provided_args):
    bulk_invalidate(**provided_args)
