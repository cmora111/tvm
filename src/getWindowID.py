#!/usr/bin/env python3

from xdo import Xdo

xdo = Xdo()
winid = xdo.select_window_with_click()
print(hex(winid))
