"""Content-addressed attachment store under <data>/media/<sha256[:2]>/<sha256>."""
from __future__ import annotations
import base64, hashlib, os, re, tempfile
from pathlib import Path

DIGEST = re.compile(r'[0-9a-f]{64}')
MAX_BYTES = int(os.environ.get('CHATARCHIVE_MEDIA_MAX_BYTES', str(512*1024*1024)))
# Raster formats a browser may display inline; everything else is served as a download.
INLINE = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'}


def media_path(directory, digest):
    if not DIGEST.fullmatch(digest or ''):
        raise ValueError('Invalid media digest')
    return Path(directory)/digest[:2]/digest


class MediaStore:
    """Receives media_part/media records from an import stream and publishes verified files."""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.pending = {}

    def part(self, r):
        key = (r['source'], str(r['message_id']))
        entry = self.pending.get(key)
        if entry is None:
            self.dir.mkdir(parents=True, exist_ok=True, mode=0o750)
            fd, temp = tempfile.mkstemp(prefix='.media-', dir=self.dir)
            entry = self.pending[key] = {'file': os.fdopen(fd, 'wb'), 'temp': temp, 'hash': hashlib.sha256(), 'bytes': 0}
        chunk = base64.b64decode(r['data'], validate=True)
        entry['bytes'] += len(chunk)
        if entry['bytes'] > MAX_BYTES:
            raise ValueError('Attachment exceeds CHATARCHIVE_MEDIA_MAX_BYTES')
        entry['file'].write(chunk)
        entry['hash'].update(chunk)

    def finish(self, con, r):
        source, mid, digest = r['source'], str(r['message_id']), r.get('sha256', '')
        destination = media_path(self.dir, digest)
        entry = self.pending.pop((source, mid), None)
        if entry is not None:
            f = entry['file']
            f.flush(); os.fsync(f.fileno()); f.close()
            try:
                if entry['hash'].hexdigest() != digest or entry['bytes'] != r.get('bytes'):
                    raise ValueError('Attachment checksum mismatch: '+mid)
                if not destination.exists():
                    destination.parent.mkdir(exist_ok=True, mode=0o750)
                    os.chmod(entry['temp'], 0o640)
                    os.replace(entry['temp'], destination)
            finally:
                if os.path.exists(entry['temp']):
                    os.unlink(entry['temp'])
        elif not destination.is_file():
            raise ValueError('Attachment content was not received: '+mid)
        con.execute("UPDATE messages SET media_sha256=?,media_name=?,media_mime=?,media_bytes=?,media_state='archived' WHERE source=? AND id=?",
                    (digest, str(r.get('name') or '')[:255], str(r.get('mime') or '')[:100], destination.stat().st_size, source, mid))

    def close(self):
        for entry in self.pending.values():
            entry['file'].close()
            if os.path.exists(entry['temp']):
                os.unlink(entry['temp'])
        self.pending.clear()
