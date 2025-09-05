# -*- coding: utf-8 -*-
def classFactory(iface):
    from .cookie_saver import CookiePlugin
    return CookiePlugin(iface)