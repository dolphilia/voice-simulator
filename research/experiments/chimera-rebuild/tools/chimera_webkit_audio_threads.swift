import Darwin
import Foundation

struct WebContentAudioThreads: Encodable {
    let pid: Int32
    let names: [String]
}

let audioThreadNames: Set<String> = ["RemoteAudioDestinationProxy render thread", "WebCore: AudioWorklet"]

func processName(_ pid: Int32) -> String? {
    var buffer = [CChar](repeating: 0, count: 64)
    let size = proc_name(pid, &buffer, UInt32(buffer.count))
    guard size > 0 else { return nil }
    return String(decoding: buffer.prefix(while: { $0 != 0 }).map(UInt8.init(bitPattern:)), as: UTF8.self)
}

func audioThreads(in pid: Int32) -> [String] {
    var task = proc_taskinfo()
    let taskSize = Int32(MemoryLayout<proc_taskinfo>.size)
    guard proc_pidinfo(pid, PROC_PIDTASKINFO, 0, &task, taskSize) == taskSize else { return [] }
    var handles = [UInt64](repeating: 0, count: Int(task.pti_threadnum) + 16)
    let bytes = Int32(handles.count * MemoryLayout<UInt64>.size)
    let count = proc_pidinfo(pid, PROC_PIDLISTTHREADS, 0, &handles, bytes)
    guard count > 0 else { return [] }

    let infoSize = Int32(MemoryLayout<proc_threadinfo>.size)
    return handles.prefix(Int(count) / MemoryLayout<UInt64>.size).compactMap { handle in
        var thread = proc_threadinfo()
        guard proc_pidinfo(pid, PROC_PIDTHREADINFO, handle, &thread, infoSize) == infoSize else { return nil }
        let name = withUnsafeBytes(of: thread.pth_name) { bytes in
            String(decoding: bytes.prefix(while: { $0 != 0 }), as: UTF8.self)
        }
        return audioThreadNames.contains(name) ? name : nil
    }.sorted()
}

let uid = getuid()
let estimate = proc_listpids(UInt32(PROC_UID_ONLY), uid, nil, 0)
guard estimate > 0 else {
    FileHandle.standardError.write(Data("同じユーザーのプロセス一覧を取得できません\n".utf8))
    exit(1)
}
let pidSize = MemoryLayout<Int32>.size
var pids = [Int32](repeating: 0, count: Int(estimate) / pidSize + 32)
let count = proc_listpids(UInt32(PROC_UID_ONLY), uid, &pids, Int32(pids.count * pidSize))
guard count > 0 else {
    FileHandle.standardError.write(Data("同じユーザーのプロセス一覧を取得できません\n".utf8))
    exit(1)
}
let observed = pids.prefix(Int(count) / pidSize).filter { pid in
    pid > 0 && processName(pid) == "com.apple.WebKit.WebContent"
}.map { pid in
    WebContentAudioThreads(pid: pid, names: audioThreads(in: pid))
}.sorted { $0.pid < $1.pid }
try FileHandle.standardOutput.write(contentsOf: JSONEncoder().encode(observed))
