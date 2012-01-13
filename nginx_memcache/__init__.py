VERSION = (0, 1)


def get_version():
    version = '%s.%s' % (VERSION[0], VERSION[1])
    try:
        version = '%s.%s' % (version, VERSION[2])
    except IndexError:
        pass

    return version
