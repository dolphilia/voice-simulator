"""短いシステムトレースの間に、別プロセスを使う歌唱の計測を実行する。"""

import argparse
from contextlib import contextmanager
from ctypes import CDLL, byref, c_int
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from uuid import uuid4


STARTING_RECORDING = b'Starting recording'


def wait_for_recording(trace, timeout):
    deadline = time.monotonic() + timeout
    output = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(trace.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            chunk = os.read(trace.stdout.fileno(), 4096)
            if not chunk:
                break
            output.extend(chunk)
            if STARTING_RECORDING in output:
                return output
    sys.stderr.buffer.write(output)
    raise RuntimeError('System Traceの開始通知を受け取れません')


@contextmanager
def darwin_notification():
    name = f'org.voice-simulator.chimera.trace.{uuid4().hex}'
    system = CDLL('/usr/lib/libSystem.B.dylib')
    fd, token = c_int(-1), c_int()
    status = system.notify_register_file_descriptor(name.encode(), byref(fd), 0, byref(token))
    if status != 0:
        raise RuntimeError(f'Darwin通知を登録できません ({status})')
    try:
        yield name, fd.value
    finally:
        system.notify_cancel(token)


def wait_for_system_notification(fd):
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        if not selector.select(15) or len(os.read(fd, 4)) != 4:
            raise RuntimeError('xctraceのDarwin通知を受け取れません')


def observe_start_signals(trace, output, observed, timeout, *, darwin_fd=None, until_stdout=False):
    wanted = ('stdout_start_line_monotonic_ns' if until_stdout or darwin_fd is None else 'darwin_monotonic_ns')
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        if 'stdout_eof_monotonic_ns' not in observed and 'stdout_start_line_monotonic_ns' not in observed:
            selector.register(trace.stdout, selectors.EVENT_READ, 'stdout')
        if darwin_fd is not None and 'darwin_monotonic_ns' not in observed:
            selector.register(darwin_fd, selectors.EVENT_READ, 'darwin')
        while time.monotonic() < deadline and wanted not in observed and selector.get_map():
            events = selector.select(max(0, deadline - time.monotonic()))
            received = time.monotonic_ns()
            if not events:
                break
            for key, _ in events:
                if key.data == 'darwin':
                    if len(os.read(key.fd, 4)) != 4:
                        raise RuntimeError('xctraceのDarwin通知を読み取れません')
                    observed['darwin_monotonic_ns'] = received
                    selector.unregister(key.fileobj)
                    continue
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    observed['stdout_eof_monotonic_ns'] = received
                    continue
                observed.setdefault('stdout_first_bytes_monotonic_ns', received)
                output.extend(chunk)
                start = output.find(STARTING_RECORDING)
                if start >= 0:
                    observed.setdefault('stdout_start_marker_monotonic_ns', received)
                    if output.find(b'\n', start) >= 0:
                        observed['stdout_start_line_monotonic_ns'] = received
                        selector.unregister(key.fileobj)


@contextmanager
def recording(folder, instruments, limit, notification=None, *, attach_pid=None, output_wait=180, window=None,
              audit_start_signals=False, stdout_release_delay_ms=None):
    if audit_start_signals and notification is None:
        raise ValueError('開始時刻の同時観測にはDarwin通知が必要です')
    if stdout_release_delay_ms is not None and not audit_start_signals:
        raise ValueError('標準出力からの再生許可には開始通知の同時観測が必要です')
    target = ['--all-processes'] if attach_pid is None else ['--attach', str(attach_pid)]
    command = ['/usr/bin/xcrun', 'xctrace', 'record', *instruments, '--time-limit', limit,
               '--no-prompt', '--output', str(folder / 'audio-system.trace'), *target]
    if window is not None:
        command.extend(['--window', window])
    if notification is not None:
        command.extend(['--notify-tracing-started', notification[0]])
    with (folder / 'system-trace-command.log').open('wb') as log, subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as trace:
        observed = {} if audit_start_signals else None
        output, tail = bytearray(), b''
        try:
            if notification is None:
                log.write(wait_for_recording(trace, 15))
            elif observed is not None:
                if stdout_release_delay_ms is None:
                    observe_start_signals(trace, output, observed, 15, darwin_fd=notification[1])
                    if 'darwin_monotonic_ns' not in observed:
                        raise RuntimeError('xctraceのDarwin通知を受け取れません')
                else:
                    observe_start_signals(trace, output, observed, 15, darwin_fd=notification[1], until_stdout=True)
                    if 'stdout_start_line_monotonic_ns' not in observed:
                        raise RuntimeError('xctraceの開始行を受け取れません')
                    earliest = observed['stdout_start_line_monotonic_ns'] + stdout_release_delay_ms * 1_000_000
                    remaining = (earliest - time.monotonic_ns()) / 1e9
                    if remaining > 0:
                        observe_start_signals(trace, output, observed, remaining, darwin_fd=notification[1])
                    time.sleep(max(0, (earliest - time.monotonic_ns()) / 1e9))
            else:
                wait_for_system_notification(notification[1])
            stamp = time.time_ns(), time.monotonic_ns()
            if observed is not None:
                observed['gate_monotonic_ns'] = stamp[1]
            log.flush()
            yield stamp
            deadline = time.monotonic() + output_wait
            if observed is not None:
                observe_start_signals(trace, output, observed, min(15, output_wait),
                                      darwin_fd=notification[1] if stdout_release_delay_ms is not None else None)
            tail, _ = trace.communicate(timeout=max(0, deadline - time.monotonic()))
        except BaseException:
            if trace.poll() is None:
                trace.terminate()
            try:
                tail, _ = trace.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                trace.kill()
                tail, _ = trace.communicate()
            raise
        finally:
            if observed is not None:
                if ('stdout_start_line_monotonic_ns' in observed and 'darwin_monotonic_ns' in observed):
                    observed['start_line_and_darwin_same_poll'] = (
                        observed['stdout_start_line_monotonic_ns'] == observed['darwin_monotonic_ns'])
                (folder / 'trace-start-signals.json').write_text(json.dumps(observed) + '\n')
                log.write(output)
            log.write(tail)
    if not (folder / 'audio-system.trace').is_dir() or trace.returncode != 0:
        raise RuntimeError(f'System Traceの採取に失敗しました ({trace.returncode})')


def capture_when_ready(folder, instruments, limit, target, offset_ms, notification):
    ready = folder / 'trace-ready.json'
    with subprocess.Popen(target) as browser:
        try:
            deadline = time.monotonic() + 30
            while not ready.is_file():
                if browser.poll() is not None:
                    raise RuntimeError(f'先行音の準備前に歌唱の採取が停止しました ({browser.returncode})')
                if time.monotonic() >= deadline:
                    raise RuntimeError('先行音の準備通知を受け取れません')
                time.sleep(0.005)
            with recording(folder, instruments, limit, notification) as (epoch_ns, monotonic_ns):
                release_after_ns = monotonic_ns + offset_ms * 1_000_000
                time.sleep(max(0, (release_after_ns - time.monotonic_ns()) / 1_000_000_000))
                (folder / 'trace-release.json').write_text(json.dumps({
                    'trace_notice_epoch_ns': epoch_ns, 'release_epoch_ns': time.time_ns(),
                    'notice_to_release_ns': time.monotonic_ns() - monotonic_ns,
                    'notice_source': 'darwin' if notification is not None else 'stdout',
                }) + '\n')
            return browser.wait(timeout=45)
        finally:
            if browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    browser.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--template')
    selection.add_argument('--instrument', action='append')
    parser.add_argument('--time-limit', required=True)
    parser.add_argument('--marker-ready-offset-ms', type=int)
    parser.add_argument('--darwin-notification', action='store_true')
    argv = sys.argv[1:]
    try:
        separator = argv.index('--')
    except ValueError:
        parser.error('区切りの -- に続けて計測コマンドを指定してください')
    args = parser.parse_args(argv[:separator])
    if separator + 1 == len(argv):
        parser.error('計測コマンドを指定してください')
    target = argv[separator+1:]
    instruments = (['--template', args.template] if args.template
                   else [arg for name in args.instrument for arg in ('--instrument', name)])
    if args.marker_ready_offset_ms is not None:
        if args.marker_ready_offset_ms < 0:
            parser.error('再開までの待ち時間は0以上にしてください')
        if args.darwin_notification:
            with darwin_notification() as notification:
                return capture_when_ready(args.folder, instruments, args.time_limit, target,
                                          args.marker_ready_offset_ms, notification)
        return capture_when_ready(args.folder, instruments, args.time_limit, target, args.marker_ready_offset_ms, None)
    with recording(args.folder, instruments, args.time_limit):
        return subprocess.run(target).returncode


if __name__ == '__main__':
    raise SystemExit(main())
