"""Network policy for URLs supplied by remote media manifests."""
import ipaddress
import socket
import time
from threading import Lock
from urllib.parse import urlsplit


DNS_CACHE_SECONDS = 60
_dns_cache = {}
_dns_lock = Lock()


class UnsafeMediaUrl(ValueError):
    pass


def _public_addresses(hostname):
    now = time.monotonic()
    with _dns_lock:
        cached = _dns_cache.get(hostname)
        if cached is not None and now - cached[0] <= DNS_CACHE_SECONDS:
            return cached[1]
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise UnsafeMediaUrl('Media host could not be resolved.') from error
    addresses = {record[4][0].split('%', 1)[0] for record in records}
    if not addresses:
        raise UnsafeMediaUrl('Media host did not resolve to an address.')
    if not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise UnsafeMediaUrl('Media URLs may not target private or local addresses.')
    with _dns_lock:
        _dns_cache[hostname] = (now, addresses)
    return addresses


def validate_media_url(url):
    """Reject local/private/credential-bearing media and redirect targets."""
    try:
        parsed = urlsplit(str(url))
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise UnsafeMediaUrl('Media URL is malformed.') from error
    if parsed.scheme.lower() not in ('http', 'https') or not hostname:
        raise UnsafeMediaUrl('Media URLs must use HTTP or HTTPS.')
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeMediaUrl('Media URLs may not contain credentials.')
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeMediaUrl('Media URL port is invalid.')
    lowered = hostname.rstrip('.').lower()
    if lowered == 'localhost' or lowered.endswith(('.localhost', '.local')):
        raise UnsafeMediaUrl('Media URLs may not target local hosts.')
    try:
        address = ipaddress.ip_address(lowered.split('%', 1)[0])
    except ValueError:
        _public_addresses(lowered)
    else:
        if not address.is_global:
            raise UnsafeMediaUrl('Media URLs may not target private or local addresses.')
    return str(url)
