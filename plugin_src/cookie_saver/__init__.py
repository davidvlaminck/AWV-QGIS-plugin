# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import CookiePlugin
    return CookiePlugin(iface)