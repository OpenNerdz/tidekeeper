"""Parse the clear HLS and DASH manifest forms used by media downloads."""
import math
import re
from urllib.parse import urljoin
from xml.etree import ElementTree


def _text(value):
    return value.decode('utf-8-sig') if isinstance(value, bytes) else value


def hls_segments(content, base_url):
    urls = []
    for line in _text(content).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXT-X-KEY:') and 'METHOD=NONE' not in line:
            raise ValueError('Encrypted HLS streams are not supported.')
        if line.startswith('#EXT-X-BYTERANGE:'):
            raise ValueError('HLS byte-range segments are not supported.')
        if line.startswith('#EXT-X-MAP:'):
            match = re.search(r'URI="([^"]+)"', line)
            if match is None or 'BYTERANGE=' in line:
                raise ValueError('Unsupported HLS initialization segment.')
            urls.append(urljoin(base_url, match.group(1)))
        elif not line.startswith('#'):
            urls.append(urljoin(base_url, line))
    return urls


def hls_variants(content, base_url):
    attributes = None
    variants = []
    for line in _text(content).splitlines():
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


def dash_segments(content):
    root = ElementTree.fromstring(content)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]

    def base(parent, node):
        child = node.find('BaseURL')
        return urljoin(parent, child.text.strip()) if child is not None and child.text else parent

    def expand(pattern, representation, number, timestamp):
        values = {'RepresentationID': representation.get('id', ''),
                  'Bandwidth': representation.get('bandwidth', ''), 'Number': number, 'Time': timestamp}
        def replace(match):
            value = values[match[1]]
            return str(value).zfill(int(match[2])) if match[2] else str(value)
        result = re.sub(r'\$(RepresentationID|Bandwidth|Number|Time)(?:%0(\d+)d)?\$', replace,
                        pattern.replace('$$', '\x00')).replace('\x00', '$')
        if not result:
            raise ValueError('Empty DASH segment URL.')
        return result

    tracks = []
    for period in root.findall('Period'):
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
                        if count < 0 or len(timestamps) + count > 100000:
                            raise ValueError('Invalid or excessively large DASH timeline.')
                        timestamps.extend(current + offset * step for offset in range(count))
                        current += step * count
                elif duration is not None and int(attrs.get('duration', 0)) > 0:
                    step = int(attrs['duration'])
                    count = math.ceil(duration * scale / step)
                    if count > 100000:
                        raise ValueError('DASH timeline is too large.')
                    timestamps = [offset * step for offset in range(count)]
                else:
                    raise ValueError('DASH manifest has no finite segment timeline.')
                urls = [urljoin(prefix, expand(attrs['initialization'], rep, number, 0))]
                urls.extend(urljoin(prefix, expand(attrs['media'], rep, number + index, timestamp))
                            for index, timestamp in enumerate(timestamps))
                tracks.append(urls)
    if not tracks:
        raise ValueError('DASH manifest contains no supported audio representations.')
    return tracks
