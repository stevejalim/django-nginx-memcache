Changelog
=========

0.1
-----
#. Initial release.


0.2-alpha
-----
#. Added support for generating cache keys based on full URIs, not just the path; this means the project can be used on shared servers, or servers serving multiple sites/subdomains which may have the same URI path

#. Adding support for a database-backed lookup table of cached pages, to make mass-page invalidation easier

#. Adding support for bulk invalidation of pages associated with a particular hostname (and/or subset of those pages. eg: if Cached Page A is hyperlinked from a menu that features on all pages in the site and its title changes, you need to invalidate more than just A, but - particularly if you're serving/cacheing multiple sites - you don't want to blat the entire nginx cache.)