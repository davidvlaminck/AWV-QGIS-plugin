# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import AssetsSplitPlugin
    return AssetsSplitPlugin(iface)