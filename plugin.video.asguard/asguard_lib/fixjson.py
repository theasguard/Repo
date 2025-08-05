import datetime
import re
import kodi
import log_utils  # @UnusedImport


def fixjson(badjson):
    s = badjson
    idx = 0
    while True:
        try:
            start = s.index( '": "', idx) + 4
            end1  = s.index( '",\n',idx)
            end2  = s.index( '"\n', idx)
            if end1 < end2:
                end = end1
            else:
                end = end2
            content = s[start:end]
            content = content.replace('"', '\\"')
            s = s[:start] + content + s[end:]
            idx = start + len(content) + 6
        except:
            return s