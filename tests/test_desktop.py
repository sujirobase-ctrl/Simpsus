import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desktop import DesktopController
from src.downloaders import PreparedThread
from src.resolvers import ResolvedMedia


DATA = b'PK\x03\x04' + bytes(range(256)) * 2048


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        fail = True
        slow = 0
        ranges = []
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path.startswith('/threads/'):
                base = f'http://127.0.0.1:{self.server.server_port}'
                body = (f'<h1 class="p-title-value">Desktop QA</h1><article class="message" id="post-1"><div class="message-body">'
                        f'<a href="{base}/one.zip">One</a><a href="{base}/two.zip">Two</a></div></article>').encode()
                self.send_response(200); self.send_header('Content-Type', 'text/html')
            elif self.path == '/two.zip' and self.fail:
                self.send_response(404); body = b'missing'
            else:
                body = DATA
                header = self.headers.get('Range')
                if header:
                    self.ranges.append(header)
                    start = int(header.split('=')[1].split('-')[0])
                    body = body[start:]
                    self.send_response(206); self.send_header('Content-Range', f'bytes {start}-{len(DATA)-1}/{len(DATA)}')
                else: self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            try:
                for offset in range(0, len(body), 65536):
                    self.wfile.write(body[offset:offset+65536])
                    self.wfile.flush()
                    if self.slow: time.sleep(self.slow)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}', Handler
    server.shutdown()


def finish(controller):
    controller.worker.join(20)
    assert not controller.worker.is_alive()
    assert not controller.error, (controller.error, list(controller.logs))


def options(base, tmp):
    return dict(url=base+'/threads/qa', destination=str(tmp / 'output'), connections=1, retries=0, delay=0)


def test_real_capture_download_retry_history(tmp_path, server):
    base, handler = server
    c = DesktopController(tmp_path/'state')
    c.analyze(options(base, tmp_path), True); finish(c)
    assert [r['status'] for r in c.rows.values()] == ['ok', 'fail']
    assert c.state == 'partial' and c.recovery.pending()
    assert hashlib.sha256(next((tmp_path/'output').rglob('one.zip')).read_bytes()).digest() == hashlib.sha256(DATA).digest()
    handler.fail = False
    c.retry(); finish(c)
    assert [r['status'] for r in c.rows.values()] == ['ok', 'ok']
    assert not c.recovery.pending()
    assert len(DesktopController(tmp_path/'state').history) == 2
    c.download(); finish(c)
    assert all(r['status'] == 'skip' for r in c.rows.values())


def test_selection_and_recovery(tmp_path, server):
    base, handler = server
    c = DesktopController(tmp_path/'state')
    c.analyze(options(base, tmp_path)); finish(c)
    assert not list((tmp_path/'output').rglob('*.zip'))
    pending = c.bootstrap()['recovery'][0]
    other = DesktopController(tmp_path/'state')
    restored = other.recover(pending['id'])
    assert restored['ids'] == [0, 1] and not restored['download']
    other.download([0]); finish(other)
    assert other.rows[0]['status'] == 'ok' and other.rows[1]['status'] == 'pending'
    assert len(list((tmp_path/'output').rglob('*.zip'))) == 1


def test_partial_resume_from_saved_queue(tmp_path, server):
    base, _ = server
    c = DesktopController(tmp_path/'state')
    c.analyze(options(base, tmp_path)); finish(c)
    c.recovery.select({c.prepared.plan[0][0].state_key})
    folder = c.prepared.root/'Photos'; folder.mkdir(parents=True)
    (folder/'one.zip.part').write_bytes(DATA[:8192])
    other = DesktopController(tmp_path/'state')
    restored = other.recover(c.recovery.path.name)
    assert restored['ids'] == [0] and restored['download']
    other.download(restored['ids']); finish(other)
    assert (folder/'one.zip').read_bytes() == DATA
    assert server[1].ranges


def test_large_catalog_bounded_updates_and_redacted_report(tmp_path):
    c = DesktopController(tmp_path)
    root = tmp_path/'output'
    c._prepared(PreparedThread('Large', root, [(ResolvedMedia(f'https://host.test/{i}.zip',f'{i}.zip'),root) for i in range(12800)],20))
    assert len(c.catalog(0,999999)['items']) == 500
    p = c.poll()
    assert len(p['items']) == 500 and len(c.dirty) == 12300
    c.log('Cookie: SECRET https://host/secret C:\\Private\\file')
    assert 'SECRET' not in c.report() and 'host/' not in c.report() and 'Private' not in c.report()


@pytest.mark.parametrize('value', [-1, 0, 1.5, float('nan'), 100000])
def test_invalid_workers_rejected(tmp_path, value):
    c = DesktopController(tmp_path)
    with pytest.raises(ValueError): c._options(dict(destination=str(tmp_path/'out'), workers=value))


def test_simulation_no_media_or_recovery(tmp_path, server):
    c = DesktopController(tmp_path/'state')
    c.analyze(dict(options(server[0],tmp_path),dry_run=True),True);finish(c)
    assert not list((tmp_path/'output').rglob('*.zip'))
    assert not c.recovery.pending()


def test_process_crash_and_range_resume(tmp_path, server):
    import subprocess
    import sys
    base, handler = server
    handler.slow = .1
    config = options(base, tmp_path)
    config['include'] = 'one.zip'
    code = f'from src.desktop import DesktopController; c=DesktopController({str(tmp_path / "state")!r}); c.analyze({config!r}, True); c.worker.join()'
    process = subprocess.Popen([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1])
    try:
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            parts = list((tmp_path/'output').rglob('*.part'))
            if parts and parts[0].stat().st_size >= 65536: break
            time.sleep(.01)
        else: raise AssertionError('No partial file before crash')
        process.kill(); process.wait(timeout=5)
        partial_size = parts[0].stat().st_size
        assert 0 < partial_size < len(DATA)
        handler.slow = 0
        c = DesktopController(tmp_path/'state')
        pending = c.bootstrap()['recovery'][0]
        restored = c.recover(pending['id'])
        c.download(restored['ids']); finish(c)
        assert next((tmp_path/'output').rglob('one.zip')).read_bytes() == DATA
        assert f'bytes={partial_size}-' in handler.ranges
        assert not c.recovery.pending()
    finally:
        if process.poll() is None: process.kill(); process.wait()


def test_api_exposes_no_runtime_objects(tmp_path):
    from src.desktop import DesktopAPI
    api = DesktopAPI(DesktopController(tmp_path))
    assert all(callable(getattr(api, name)) for name in dir(api) if not name.startswith('_'))
    assert not hasattr(api, 'window') and not hasattr(api, 'recovery')


def test_simulation_preserves_previous_pending_task(tmp_path, server):
    c = DesktopController(tmp_path/'state')
    c.analyze(options(server[0], tmp_path), True); finish(c)
    previous = c.recovery.path
    assert previous.exists()
    c.analyze(dict(options(server[0], tmp_path), dry_run=True), True); finish(c)
    assert previous.exists()
