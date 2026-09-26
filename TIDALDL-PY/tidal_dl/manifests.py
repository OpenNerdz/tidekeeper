"""Parse the clear HLS and DASH manifest forms used by media downloads."""
import math
import re
from urllib.parse import urljoin

from defusedxml import ElementTree


MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_NODES = 200000
MAX_SEGMENTS = 100000
MAX_EXPANDED_URL_BYTES = 16 * 1024 * 1024
MAX_TEMPLATE_WIDTH = 20


class ProtectedManifestError(ValueError):
    """The manifest requires an encryption scheme this downloader cannot play."""


def _text(value):
    if isinstance(value, bytes):
        if len(value) > MAX_MANIFEST_BYTES:
            raise ValueError('Manifest is too large.')
        return value.decode('utf-8-sig')
    value = str(value)
    if len(value.encode('utf-8')) > MAX_MANIFEST_BYTES:
        raise ValueError('Manifest is too large.')
    return value


def _xml_root(content):
    root = ElementTree.fromstring(_text(content))
    if sum(1 for _ in root.iter()) > MAX_MANIFEST_NODES:
        raise ValueError('DASH manifest contains too many XML nodes.')
    return root


def hls_segments(content, base_url):
    urls = []
    expanded_bytes = 0
    lines = [line.strip() for line in _text(content).strip().splitlines()]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXT-X-KEY:'):
            method = re.search(r'(?:^|,)METHOD=([^,]+)', line.split(':', 1)[1])
            if method is None or method[1] != 'NONE':
                raise ValueError('Encrypted HLS streams are not supported.')
        if line.startswith('#EXT-X-STREAM-INF:'):
            raise ValueError('Expected a media playlist, not an HLS variant list.')
        if line.startswith('#EXT-X-BYTERANGE:'):
            raise ValueError('HLS byte-range segments are not supported.')
        location = None
        if line.startswith('#EXT-X-MAP:'):
            match = re.search(r'URI="([^"]+)"', line)
            if match is None or 'BYTERANGE=' in line:
                raise ValueError('Unsupported HLS initialization segment.')
            location = urljoin(base_url, match.group(1))
        elif not line.startswith('#'):
            location = urljoin(base_url, line)
        if location is not None:
            expanded_bytes += len(location.encode('utf-8'))
            if expanded_bytes > MAX_EXPANDED_URL_BYTES:
                raise ValueError('Expanded HLS manifest is too large.')
            urls.append(location)
        if len(urls) > MAX_SEGMENTS:
            raise ValueError('HLS manifest has too many segments.')
    if not lines or lines[0] != '#EXTM3U':
        raise ValueError('Invalid HLS playlist header.')
    # RFC 8216 section 4.3.3.5: VOD playlists cannot change. They are
    # complete even when a provider omits the end marker.
    if '#EXT-X-ENDLIST' not in lines and '#EXT-X-PLAYLIST-TYPE:VOD' not in lines:
        raise ValueError('Live or unfinished HLS playlists are not supported.')
    return urls


def hls_variants(content, base_url):
    attributes = None
    variants = []
    lines = _text(content).strip().splitlines()
    if not lines or lines[0] != '#EXTM3U':
        raise ValueError('Invalid HLS playlist header.')
    for line in lines:
        line = line.strip()
        if line.startswith('#EXT-X-STREAM-INF:'):
            resolution = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
            codecs = re.search(r'CODECS="([^"]+)"', line)
            attributes = (resolution, codecs)
        elif line and not line.startswith('#') and attributes:
            resolution, codecs = attributes
            if resolution:
                variants.append((int(resolution[1]), int(resolution[2]),
                                 codecs[1] if codecs else '', urljoin(base_url, line)))
            attributes = None
    return sorted(variants, key=lambda item: item[1])


def _seconds(value):
    match = re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', value or '')
    if not match:
        return None
    return sum(float(part or 0) * factor for part, factor in zip(match.groups(), (3600, 60, 1)))


def dash_representations(content):
    """Return bounded, clear audio representations and their quality facts."""
    root = _xml_root(content)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
        if element.tag == 'ContentProtection':
            # Returning these URLs would save encrypted media as a successful
            # download. Reject the manifest before extracting any segments.
            raise ProtectedManifestError('DRM-protected DASH streams are not supported.')

    def base(parent, node):
        child = node.find('BaseURL')
        return urljoin(parent, child.text.strip()) if child is not None and child.text else parent

    def expand(pattern, representation, number, timestamp):
        values = {'RepresentationID': representation.get('id', ''),
                  'Bandwidth': representation.get('bandwidth', ''), 'Number': number, 'Time': timestamp}
        def replace(match):
            value = values[match[1]]
            width = int(match[2] or 0)
            if width > MAX_TEMPLATE_WIDTH:
                raise ValueError('DASH number formatting width is too large.')
            return str(value).zfill(width)
        result = re.sub(r'\$(RepresentationID|Bandwidth|Number|Time)(?:%0(\d+)d)?\$', replace,
                        pattern.replace('$$', '\x00')).replace('\x00', '$')
        if not result:
            raise ValueError('Empty DASH segment URL.')
        return result

    tracks = []
    periods = root.findall('Period')
    if len(periods) != 1:
        raise ValueError('DASH requires a single complete period; multi-period audio is not supported.')
    expanded_count = expanded_bytes = 0
    for period in periods:
        duration = _seconds(period.get('duration'))
        if duration is None:
            duration = _seconds(root.get('mediaPresentationDuration'))
            if duration is not None:
                duration -= _seconds(period.get('start')) or 0
        for adaptation in period.findall('AdaptationSet'):
            for rep in adaptation.findall('Representation'):
                media_type = rep.get('mimeType', adaptation.get('mimeType', ''))
                if adaptation.get('contentType') != 'audio' and not media_type.startswith('audio/'):
                    continue
                templates = [node.find('SegmentTemplate') for node in (period, adaptation, rep)]
                attrs, timeline = {}, None
                for template in templates:
                    if template is not None:
                        attrs.update(template.attrib)
                        found = template.find('SegmentTimeline')
                        if found is not None:
                            timeline = found
                if not attrs.get('initialization') or not attrs.get('media'):
                    raise ValueError('DASH requires initialization and media segment templates.')
                prefix = base(base(base(base('', root), period), adaptation), rep)
                number = int(attrs.get('startNumber', 1))
                scale = int(attrs.get('timescale', 1))
                if scale <= 0:
                    raise ValueError('Invalid DASH timescale.')
                timestamps = []
                if timeline is not None:
                    current = 0
                    entries = list(timeline.findall('S'))
                    for index, entry in enumerate(entries):
                        current = int(entry.get('t', current))
                        step = int(entry.get('d', 0))
                        if step <= 0:
                            raise ValueError('Invalid DASH segment duration.')
                        repeat = int(entry.get('r', 0))
                        if repeat < 0:
                            following = entries[index + 1] if index + 1 < len(entries) else None
                            end = int(following.get('t')) if following is not None and following.get('t') else None
                            if end is None and duration is not None:
                                end = duration * scale + int(attrs.get('presentationTimeOffset', 0))
                            if end is None:
                                raise ValueError('Unbounded DASH timeline is not supported.')
                            repeat = math.ceil((end - current) / step) - 1
                        count = repeat + 1
                        if count < 0 or len(timestamps) + count > MAX_SEGMENTS:
                            raise ValueError('Invalid or excessively large DASH timeline.')
                        timestamps.extend(current + offset * step for offset in range(count))
                        current += step * count
                elif duration is not None and int(attrs.get('duration', 0)) > 0:
                    step = int(attrs['duration'])
                    count = math.ceil(duration * scale / step)
                    if count > MAX_SEGMENTS:
                        raise ValueError('DASH timeline is too large.')
                    timestamps = [offset * step for offset in range(count)]
                else:
                    raise ValueError('DASH manifest has no finite segment timeline.')
                if not timestamps or expanded_count + len(timestamps) + 1 > MAX_SEGMENTS:
                    raise ValueError('DASH manifest has no media segments or too many segments.')
                urls = []
                for pattern, segment_number, timestamp in [
                    (attrs['initialization'], number, 0),
                    *((attrs['media'], number + index, timestamp) for index, timestamp in enumerate(timestamps)),
                ]:
                    location = urljoin(prefix, expand(pattern, rep, segment_number, timestamp))
                    expanded_bytes += len(location.encode('utf-8'))
                    if expanded_bytes > MAX_EXPANDED_URL_BYTES:
                        raise ValueError('Expanded DASH manifest is too large.')
                    urls.append(location)
                expanded_count += len(urls)
                representation_id = rep.get('id', '')
                bit_depth = rep.get('audioBitDepth', adaptation.get('audioBitDepth', ''))
                if not bit_depth:
                    # Current TIDAL manifests also encode this in identifiers
                    # such as FLAC,192000,24 and FLAC_HIRES,192000,24.
                    match = re.fullmatch(
                        r'FLAC(?:_[A-Z0-9]+)*,\d+,(\d{1,2})', representation_id, re.IGNORECASE,
                    )
                    bit_depth = match.group(1) if match else ''
                sample_rate = rep.get('audioSamplingRate', adaptation.get('audioSamplingRate', ''))
                channels = ''
                channel_node = rep.find('AudioChannelConfiguration')
                if channel_node is None:
                    channel_node = adaptation.find('AudioChannelConfiguration')
                if channel_node is not None:
                    channels = channel_node.get('value', '')

                def integer(value):
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        return None

                tracks.append({
                    'urls': urls,
                    'id': representation_id,
                    'codec': rep.get('codecs', adaptation.get('codecs', '')),
                    'mimeType': media_type,
                    'bandwidth': integer(rep.get('bandwidth')),
                    'sampleRate': integer(sample_rate),
                    'bitDepth': integer(bit_depth),
                    'channels': integer(channels),
                })
    if not tracks:
        raise ValueError('DASH manifest contains no supported audio representations.')
    return tracks


def _quality_key(representation):
    codec = str(representation.get('codec') or '').lower()
    lossless = int('flac' in codec or 'alac' in codec)
    return (
        lossless,
        int(representation.get('bitDepth') or 0),
        int(representation.get('sampleRate') or 0),
        int(representation.get('bandwidth') or 0),
        int(representation.get('channels') or 0),
    )


def best_dash_representation(content):
    """Select the highest-fidelity representation instead of trusting XML order."""
    return max(dash_representations(content), key=_quality_key)


def dash_segments(content):
    """Backward-compatible URL-only view used by older callers and tests."""
    return [item['urls'] for item in dash_representations(content)]
