Django Nginx Memcache
=====================
Provides a view decorator. Use it to cache content in Memcache for nginx to
retrieve.

Provides functions and signals to use to invalidate the cache, too.

The cache keys are hashed using an md5 of the the request path *without*
GET parameters,

In progress 
-----------

IMPORTANT: If this has anything listed here, the code must be treated as unstable, even if it's on a master branch

To do
-----

#. Add support for manually pushing a page to the cache via a function call - this will enable eager cacheing

Installation
------------

#. The usual pip or easy_install from `github <https://github.com/torchbox/django-nginx-memcache>`_::

    pip install -e git://github.com/torchbox/django-nginx-memcache#egg=django-nginx-memcache

#. Add ``nginx_memcache`` to your installed apps::

    INSTALLED_APPS = (
        # ...
        'nginx_memcache',
        # ...
    )

#. If you wish to use the DB-backed cached-page lookup (so that you know what pages may have been cached, and so may need invalidating), run `syncdb` to add the required table:

    ./manage.py syncdb nginx_memcache

#. Let your app/project know about the cache-invalidation signals by importing them in a module you *know* will always be loaded (eg the `__init__.py` for your core app)

    from nginx_memcache.signals import (
        handle_single_page_invalidation,
        handle_multiple_page_invalidation
    )

#. Set the default cache timeout::

    CACHE_NGINX = True
    CACHE_NGINX_TIME = 3600 * 24  # 1 day, in seconds
    
    # Default backend to use from settings.CACHES
    # May need to update the nginx conf if this is changed
    CACHE_NGINX_ALIAS = 'default'
    
    # Whether or not a DB-backed lookup table is useds 
    CACHE_NGINX_USE_LOOKUP_TABLE = False  # default is False

    # Whether or not to cache HTTPS requests, and how to identify HTTPS requests from headers
    # (eg, if SSL termination has taken place before Django is hit)
    CACHE_NGINX_INCLUDE_HTTPS = True  # default is True
    CACHE_NGINX_ALTERNATIVE_SSL_HEADERS' = (
        ('X-Forwarded-Proto', 'HTTPS'),
        ('X-Forwarded-SSL', 'on')
    )  # values in tuples are header, value that confirms was a HTTPS request
    # the examples above are the defaults. See middleware.py
    
#. Setup Memcached appropriately as described in `Django's cache framework docs <http://docs.djangoproject.com/en/dev/topics/cache/#memcached>`_.

#. Install Nginx with the `set_misc <https://github.com/agentzh/set-misc-nginx-module>`_ or `set_hash module <https://github.com/simpl/ngx_http_set_hash>`_. This is required to compute md5 cache keys from within Nginx. (See installing nginx below).

#. Configure Nginx for direct Memcached page retrieval, i.e::

    # Nginx host configuration for demosite. 
    #
    # Attempts to serve a page from memcache, falling
    # back to Django if it's not available. 
    # This example version also skips trying to get pages 
    # from memcache if the page was accessed over SSL.
                             
    upstream gunicorn_demosite {
        server 127.0.0.1:8003 fail_timeout=0;
    }

    server {
        listen 80 default_server;
        
        # Listen for all server names - lots of sites will be CNAMED
        # to this server, and we won't know what/which.

        # We listen on 80 because, behind ELB, everything is non-SSL
        # and anything that was SSL has the X-Forwarded-Proto: HTTPS
        # header appended to the request, which we'll look for.

        server_name _;

        access_log /var/log/nginx/demosite.access.log;
        error_log /var/log/nginx/demosite.error.log;

        # temporary logging during development
        log_format hashedgeneratedkey $hash_key;
        log_format realkey $memcached_key;
        access_log  /var/log/nginx/keys.log  hashedgeneratedkey;
        access_log  /var/log/nginx/keys.log  realkey;
        # are we getting the HTTPS header?
        log_format http_x_forwarded_proto $http_x_forwarded_proto;
        access_log  /var/log/nginx/keys.log  http_x_forwarded_proto;

        location /static/ {
                root /usr/local/django/demosite/;
        }

        location /media/ {
                root /usr/local/django/virtualenvs/demosite/lib/python2.7/site-packages/django/contrib/admin/;
        }

        location @gunicorn {
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header Host $http_host;
                proxy_redirect off;

	        proxy_pass http://gunicorn_demosite;

                client_max_body_size 10m;
        }

        location @cache_miss {
                # Pass on the request to gunicorn, creating
                # a URI with the hostname as well as the path                                                                                                  
                # See the docs if $is_args$args is confusing

                set $caught_uri $http_host$uri$is_args$args;
                try_files $caught_uri @gunicorn;
        }

        location @memcache_check {

                # Otherwise, see if we can serve things from memcache.

                # Extract cache key args and cache key. 
                if ($http_cookie ~* "pv=([^;]+)(?:;|$)") {
                    set $page_version $1;
                }

                # If you are running multiple sites off the same server, 
                # the cache key to include the domain, too, which nginx
                # doesn't consider part of the $uri. (SJ: it ought to do, but doesn't)

                set_md5 $hash_key $http_host$uri&pv=$page_version;
                # make sure that this matches the CACHE_PREFIX in project settings
                set $django_cache_prefix ps;
                set $django_cache_version 1;
                set $memcached_key $django_cache_prefix:$django_cache_version:$hash_key;

                recursive_error_pages on;

                set $fallthrough_uri null;
                  
                # Hit memcache, to see if the page is there 

                default_type       text/html;
                memcached_pass     127.0.0.1:11211;

                # We hand off all of these to @cache_miss and its descendent handlers.
                # The = means the handlers determine the error code, which is a Good Thing     

                error_page         401 = @cache_miss;
                error_page         403 = @cache_miss;
                error_page         404 = @cache_miss;
                error_page         405 = @cache_miss;

                # Note that it is not permitted to have a try_files in the same
                # location block as a memcache_pass
        }

        location / {

                recursive_error_pages on;
        
                set $caught_uri $http_host$uri$is_args$args;

                # Default is to try memcache
                set $destination_block @memcache_check; 

                # If we've got proof that it was an SSL cert, just 
                # short-cut to @gunicorn via the @cache_miss location
                # (ELB sets X-Forwarded-Proto: HTTPS for instance )
                if ($http_x_forwarded_proto = HTTPS){
                    set $destination_block @cache_miss;
                }

                # hand off to whichever block was appropriate  
                try_files $caught_uri $destination_block;

                # SJ: not entirely sure about this - needs more 
                # testing as it shouldn't, to my mind, be needed

                error_page         401 = $destination_block;
                error_page         403 = $destination_block;
                error_page         404 = $destination_block;
                error_page         405 = $destination_block;

        }
}   

Installing Nginx
~~~~~~~~~~~~~~~~

These instructions apply for Ubuntu 11.04 and above::

    # install all dependencies
    sudo aptitude install libc6 libpcre3 libpcre3-dev libpcrecpp0 libssl0.9.8 libssl-dev zlib1g zlib1g-dev lsb-base

    # download nginx
    wget http://nginx.org/download/nginx-1.0.11.tar.gz
    tar -zxf nginx-1.0.11.tar.gz
    rm nginx-1.0.11.tar.gz
    cd nginx-1.0.11/

    # download modules
    wget https://github.com/simpl/ngx_devel_kit/zipball/v0.2.17 -O ngx_devel_kit.zip
    unzip ngx_devel_kit.zip
    wget https://github.com/agentzh/set-misc-nginx-module/zipball/v0.22rc4 -O set-misc-nginx-module.zip
    unzip set-misc-nginx-module.zip
    wget https://github.com/agentzh/echo-nginx-module/zipball/v0.37rc7 -O echo-nginx-module.zip
    unzip echo-nginx-module.zip

    # configure and install
    ./configure \
        --add-module=simpl-ngx_devel_kit-bc97eea \
        --add-module=agentzh-set-misc-nginx-module-290d6cb \
        --add-module=agentzh-echo-nginx-module-b7ea185 \
        --prefix=/usr \
        --pid-path=/var/run/nginx.pid \
        --lock-path=/var/lock/nginx.lock \
        --http-log-path=/var/log/nginx/access.log \
        --error-log-path=/var/log/nginx/error.log \
        --http-client-body-temp-path=/var/lib/nginx/body \
        --conf-path=/etc/nginx/nginx.conf \
        --with-http_flv_module \
        --with-http_ssl_module \
        --with-http_gzip_static_module \
        --http-proxy-temp-path=/var/lib/nginx/proxy \
        --with-http_stub_status_module \
        --http-fastcgi-temp-path=/var/lib/nginx/fastcgi \
        --http-uwsgi-temp-path=/var/lib/nginx/uwsgi \
        --http-scgi-temp-path=/var/lib/nginx/scgi
    make
    sudo make install

    # Done, now configure your nginx.


Usage
-----

nginx_memcache.decorators.cache_page_nginx
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``cache_page_nginx`` decorator caches the view's response content in Memcache. Any arguments are optional and outlined below.

Example::

    from nginx_memcache.decorators import cache_page_nginx

    @cache_page_nginx
    def my_view(request):
        ...

This will cache the view's response string in Memcache, and hereafter Nginx
will serve from Memcache directly, without hitting your Django server,
until the cache key expires.

Optional parameters
+++++++++++++++++++

``cache_timeout``
  Defaults to ``settings.CACHE_NGINX_TIME`` if not specified.

``page_version_fn``
  Use this to return a stringifiable version of the page, depending on the
  request. Example::

    def get_page_version(request):
        if request.user.is_authenticated():
            return 'authed'
        return 'anonymous'

``anonymous_only``
  Don't cache the page unless the user is anonymous, i.e. not authenticated.

Usage with forms and CSRF
~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to embed forms on a cached page, you can leave out the context `{{ csrf() }}` or `{% csrf_token %}` and, instead, append it to all forms using JavaScript post page-load, or when a button is clicked.

Here's example JS and Django code for it::

    // JS code
    $.ajax({
        url: // your csrf url,
        type: 'GET',
        data: {type: 'login'},  // only if you need a session id for cookie login
        dataType: 'json',
        success: function(data) {
            $('form').each(function() {
                $(this).append(
                    '<input type=hidden name=csrfmiddlewaretoken ' +
                        ' value="' + data.token + '">');
            });
        }
    });

    // Django code
    # views.py, don't forget to add to urls.py
    def get_csrf(request):
        if request.GET.get('type') == 'login':
            request.session.set_test_cookie()
        return JSONResponse({
            'status': 1,
            'token': getattr(request, 'csrf_token', 'NOTPROVIDED')
        })


Full List of Settings
~~~~~~~~~~~~~~~~~~~~~

``CACHE_NGINX``
  Set this to False to disable any caching. E.g. for testing, staging...

``CACHE_NGINX_TIME``
  Default cache timeout.

``CACHE_NGINX_ALIAS``
  Which cache backend to use from `settings.CACHES <https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-CACHES>`_

``CACHE_MINIFY_HTML``
  Will cache a HTML minified version of the response output. Default = False.

Contributing
============
If you'd like to fix a bug, add a feature, etc

#. Start by opening an issue.
    Be explicit so that project collaborators can understand and reproduce the
    issue, or decide whether the feature falls within the project's goals.
    Code examples can be useful, too.

#. File a pull request.
    You may write a prototype or suggested fix.

#. Check your code for errors, complaints.
    Use `check.py <https://github.com/jbalogh/check>`_

#. Write and run tests.
    Write your own test showing the issue has been resolved, or the feature
    works as intended.

Running Tests
=============
To run the tests::

    python manage.py test nginx_memcache
