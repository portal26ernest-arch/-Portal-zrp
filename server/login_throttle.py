"""Bounded process-local login budgets, shared across credential aliases."""
from collections import deque
from ipaddress import ip_address
import math
from threading import Lock
import time

class LoginLimiter:
    def __init__(self,clock=time.monotonic,max_keys=4096):
        self.clock=clock;self.max_keys=max_keys;self._buckets={};self._lock=Lock()

    def consume(self,key,limit,window):
        """Return Retry-After seconds, or zero after an atomic reservation."""
        with self._lock:
            now=self.clock()
            # Only expired buckets may be removed: capacity cannot evict a lockout.
            if key not in self._buckets and len(self._buckets)>=self.max_keys:
                expired=[k for k,(until,_) in self._buckets.items() if until<=now]
                for k in expired:del self._buckets[k]
                if len(self._buckets)>=self.max_keys:return math.ceil(window)
            _,events=self._buckets.get(key,(0,deque()))
            while events and events[0]<=now-window:events.popleft()
            if len(events)>=limit:return max(1,math.ceil(events[0]+window-now))
            events.append(now);self._buckets[key]=(now+window,events)
            return 0

def client_ip(peer,headers,trusted_proxies=()):
    """Forwarded IP is used only from explicitly trusted, overwriting proxies."""
    try:
        address=ip_address(peer)
        trusted={ip_address(value) for value in trusted_proxies}
        if address in trusted:
            value=headers.get('X-Real-IP','')
            if value:return str(ip_address(value))
        return str(address)
    except ValueError:return str(peer)
