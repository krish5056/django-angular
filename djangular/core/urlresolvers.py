# -*- coding: utf-8 -*-
from inspect import isclass
from django.utils import six
from django.utils.module_loading import import_by_path
from django.core.urlresolvers import (get_resolver, get_urlconf, get_script_prefix,
    get_ns_resolver, iri_to_uri, resolve, reverse, NoReverseMatch)
from django.core.exceptions import ImproperlyConfigured
from djangular.views.mixins import JSONResponseMixin


def urls_by_namespace(namespace, urlconf=None, args=None, kwargs=None, prefix=None, current_app=None):
    """
    Return a dictionary containing the name together with the URL of all configured
    URLs specified for this namespace.
    """
    if urlconf is None:
        urlconf = get_urlconf()
    resolver = get_resolver(urlconf)
    args = args or []
    kwargs = kwargs or {}

    if prefix is None:
        prefix = get_script_prefix()

    if not namespace or not isinstance(namespace, six.string_types):
        raise AttributeError('Attribute namespace must be of type string')
    path = namespace.split(':')
    path.reverse()
    resolved_path = []
    ns_pattern = ''
    while path:
        ns = path.pop()

        # Lookup the name to see if it could be an app identifier
        try:
            app_list = resolver.app_dict[ns]
            # Yes! Path part matches an app in the current Resolver
            if current_app and current_app in app_list:
                # If we are reversing for a particular app,
                # use that namespace
                ns = current_app
            elif ns not in app_list:
                # The name isn't shared by one of the instances
                # (i.e., the default) so just pick the first instance
                # as the default.
                ns = app_list[0]
        except KeyError:
            pass

        try:
            extra, resolver = resolver.namespace_dict[ns]
            resolved_path.append(ns)
            ns_pattern = ns_pattern + extra
        except KeyError as key:
            if resolved_path:
                raise NoReverseMatch("%s is not a registered namespace inside '%s'" %
                    (key, ':'.join(resolved_path)))
            else:
                raise NoReverseMatch("%s is not a registered namespace" % key)
    resolver = get_ns_resolver(ns_pattern, resolver)
    return dict((name, iri_to_uri(resolver._reverse_with_prefix(name, prefix, *args, **kwargs)))
                for name in resolver.reverse_dict.keys() if isinstance(name, six.string_types))


def _get_remote_methods_for(view_object, url):
    # view_object can be a view class or instance
    result = {}
    for field in dir(view_object):
        member = getattr(view_object, field, None)
        if callable(member) and hasattr(member, 'allow_rmi'):
            config = {
                'url': url,
                'method': getattr(member, 'allow_rmi'),
                'headers': {'DjNg-Remote-Method': field},
            }
            result.update({field: config})
    return result


def get_all_remote_methods(resolver=None, ns_prefix=''):
    """
    Returns a dictionary to be used for calling ``djangoCall.configure()``, which itself extends the
    Angular API to the client, offering him to call remote methods.
    """
    if not resolver:
        resolver = get_resolver(get_urlconf())
    result = {}
    for name in resolver.reverse_dict.keys():
        if not isinstance(name, six.string_types):
            continue
        try:
            url = reverse(ns_prefix + name)
            resmgr = resolve(url)
            ViewClass = import_by_path('{0}.{1}'.format(resmgr.func.__module__, resmgr.func.__name__))
            if isclass(ViewClass) and issubclass(ViewClass, JSONResponseMixin):
                result[name] = _get_remote_methods_for(ViewClass, url)
        except (NoReverseMatch, ImproperlyConfigured):
            pass
    for namespace, ns_pattern in resolver.namespace_dict.items():
        sub_res = get_all_remote_methods(ns_pattern[1], ns_prefix + namespace + ':')
        if sub_res:
            result[namespace] = sub_res
    return result


def get_current_remote_methods(view):
    if isinstance(view, JSONResponseMixin):
        return _get_remote_methods_for(view, view.request.path_info)
