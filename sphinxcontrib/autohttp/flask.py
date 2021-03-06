"""
    sphinxcontrib.autohttp.flask
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The sphinx.ext.autodoc-style HTTP API reference builder (from Flask)
    for sphinxcontrib.httpdomain.

    :copyright: Copyright 2011 by Hong Minhee
    :license: BSD, see LICENSE for details.

"""

import re
import six

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.statemachine import ViewList

from sphinx.util import force_decode
from sphinx.util.compat import Directive
from sphinx.util.nodes import nested_parse_with_titles
from sphinx.util.docstrings import prepare_docstring
from sphinx.pycode import ModuleAnalyzer

from sphinxcontrib import httpdomain
from sphinxcontrib.autohttp.common import http_directive, import_object


def translate_werkzeug_rule(rule):
    from werkzeug.routing import parse_rule
    buf = six.StringIO()
    for conv, arg, var in parse_rule(rule):
        if conv:
            buf.write('(')
            if conv != 'default':
                buf.write(conv)
                buf.write(':')
            buf.write(var)
            buf.write(')')
        else:
            buf.write(var)
    return buf.getvalue()


def get_routes(app):
    for rule in app.url_map.iter_rules():
        path = translate_werkzeug_rule(rule.rule)
        methods = rule.methods.difference(['OPTIONS', 'HEAD'])
        for method in methods:
            yield method, path, rule.endpoint


def get_route_order_key(item):
    FIXED_ORDER = ('GET', 'POST', 'PUT', 'DELETE')
    method, path, endpoint = item

    method_index = len(FIXED_ORDER)
    if method in FIXED_ORDER:
        method_index = FIXED_ORDER.index(method)

    return "%s__%03d__%02d" % (endpoint, len(path), method_index)

def get_routes_in_order(app):
    ordered_routes = sorted(get_routes(app), key=get_route_order_key)
    return ordered_routes

class AutoflaskDirective(Directive):

    has_content = True
    required_arguments = 1
    option_spec = {'endpoints': directives.unchanged,
                   'blueprints': directives.unchanged,
                   'undoc-endpoints': directives.unchanged,
                   'undoc-blueprints': directives.unchanged,
                   'undoc-static': directives.unchanged,
                   'include-empty-docstring': directives.unchanged}

    @property
    def endpoints(self):
        endpoints = self.options.get('endpoints', None)
        if not endpoints:
            return None
        return frozenset(re.split(r'\s*,\s*', endpoints))

    @property
    def undoc_endpoints(self):
        undoc_endpoints = self.options.get('undoc-endpoints', None)
        if not undoc_endpoints:
            return frozenset()
        return frozenset(re.split(r'\s*,\s*', undoc_endpoints))

    @property
    def blueprints(self):
        blueprints = self.options.get('blueprints', None)
        if not blueprints:
            return None
        return frozenset(re.split(r'\s*,\s*', blueprints))

    @property
    def undoc_blueprints(self):
        undoc_blueprints = self.options.get('undoc-blueprints', None)
        if not undoc_blueprints:
            return frozenset()
        return frozenset(re.split(r'\s*,\s*', undoc_blueprints))

    def make_rst(self):
        app = import_object(self.arguments[0])
        for method, path, endpoint in get_routes_in_order(app):
            try:
                blueprint, _, endpoint_internal = endpoint.rpartition('.')
                if self.blueprints and blueprint not in self.blueprints:
                    continue
                if blueprint in self.undoc_blueprints:
                    continue
            except ValueError:
                pass  # endpoint is not within a blueprint

            if self.endpoints and endpoint not in self.endpoints:
                continue
            if endpoint in self.undoc_endpoints:
                continue
            try:
                static_url_path = app.static_url_path # Flask 0.7 or higher
            except AttributeError:
                static_url_path = app.static_path # Flask 0.6 or under
            if ('undoc-static' in self.options and endpoint == 'static' and
                path == static_url_path + '/(path:filename)'):
                continue
            view = app.view_functions[endpoint]
            docstring = view.__doc__ or ''
            if hasattr(view, 'view_class'):
                meth_func = getattr(view.view_class, method.lower(), None)
                if meth_func and meth_func.__doc__:
                    docstring = meth_func.__doc__
            if not isinstance(docstring, six.text_type):
                analyzer = ModuleAnalyzer.for_module(view.__module__)
                docstring = force_decode(docstring, analyzer.encoding)
    
            if not docstring and 'include-empty-docstring' not in self.options:
                continue
            docstring = prepare_docstring(docstring)
            for line in http_directive(method, path, docstring):
                yield line

    def run(self):
        node = nodes.section()
        node.document = self.state.document
        result = ViewList()
        for line in self.make_rst():
            result.append(line, '<autoflask>')
        nested_parse_with_titles(self.state, result, node)
        return node.children


def setup(app):
    if 'http' not in app.domains:
        httpdomain.setup(app)
    app.add_directive('autoflask', AutoflaskDirective)

