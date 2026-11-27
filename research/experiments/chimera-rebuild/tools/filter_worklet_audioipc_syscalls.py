"""xctraceのsyscall表から、指定した実験プロセスのソケット操作を抜き出す。"""

import argparse
from collections import Counter
import json
from pathlib import Path
from xml.etree import ElementTree


SOCKET_CALLS = ('sendmsg', 'recvmsg', 'sendto', 'recvfrom', 'read', 'write', 'readv', 'writev')
VALUE_TAGS = {'start-time', 'duration', 'syscall', 'syscall-arg', 'syscall-return', 'pid', 'tid'}
CHILD_ID = {'thread': 'tid', 'process': 'pid'}


def field_value(cell, values):
    if 'ref' in cell.attrib:
        return values[cell.attrib['ref']]
    child = cell.find(CHILD_ID[cell.tag]) if cell.tag in CHILD_ID else None
    return cell.text if child is None else field_value(child, values)


def filter_targets(source, targets):
    selected = {(str(pid), str(tid) if tid is not None else None): (Counter(), []) for pid, tid in targets}
    values = {}
    schema = None
    total = 0
    for event, element in ElementTree.iterparse(source, events=('start', 'end')):
        if event == 'start' and element.tag == 'node':
            node = element
        if event != 'end':
            continue
        if element.tag == 'schema':
            schema = [col.findtext('mnemonic') for col in element]
        if element.tag != 'row':
            continue
        for cell in element.iter():
            identity = cell.get('id')
            if identity is not None and (cell.tag in VALUE_TAGS or cell.tag in CHILD_ID):
                values[identity] = field_value(cell, values)
        row = dict(zip(schema, element))
        total += 1
        process_id = field_value(row['process'], values)
        start = int(field_value(row['start'], values))
        thread_id = field_value(row['thread'], values)
        scoped = selected.get((process_id, thread_id))
        process = selected.get((process_id, None))
        outputs = [output for output in (scoped, process) if output is not None]
        if outputs:
            name = field_value(row['call'], values).removeprefix('BSC_').removesuffix('_nocancel')
            duration = field_value(row['duration'], values)
            fd = field_value(row['arg1'], values)
            size = field_value(row['return'], values)
            for counts, events in outputs:
                counts[name] += 1
                if (name in SOCKET_CALLS and thread_id is not None and duration is not None
                        and fd is not None and size is not None and int(size) > 0):
                    events.append({'syscall': name, 'start_ns': start, 'end_ns': start + int(duration),
                                   'tid': int(thread_id), 'fd': int(fd), 'bytes': int(size)})
        node.remove(element)
    if schema is None:
        raise ValueError('syscall表のスキーマを見つけられません')
    return [{'pid': pid, 'tid': tid, 'table_rows': total, 'syscalls': dict(counts),
             'last_row_start_ns': start if total else None, 'completed_io': events}
            for pid, tid in targets
            for counts, events in [selected[(str(pid), str(tid) if tid is not None else None)]]]


def filter_table(source, pid, tid=None):
    return filter_targets(source, [(pid, tid)])[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('syscall_xml', type=Path)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--tid', type=int)
    args = parser.parse_args()
    print(json.dumps(filter_table(args.syscall_xml, args.pid, args.tid), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
