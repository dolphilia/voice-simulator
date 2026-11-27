import CoreAudio
import Darwin
import Foundation

struct OutputProcess: Encodable {
    let pid: pid_t
    let object: AudioObjectID
    let bundleID: String
    let runningOutput: Bool
}

func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

func property<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector, into result: inout T) -> Bool {
    var attr = address(selector)
    var size = UInt32(MemoryLayout<T>.size)
    return withUnsafeMutablePointer(to: &result) { pointer in
        AudioObjectGetPropertyData(object, &attr, 0, nil, &size, pointer) == noErr
    }
}

func processes() throws -> [AudioObjectID] {
    let system = AudioObjectID(kAudioObjectSystemObject)
    var list = address(kAudioHardwarePropertyProcessObjectList)
    let unit = UInt32(MemoryLayout<AudioObjectID>.stride)
    for _ in 0..<3 {
        var count: UInt32 = 0
        let status = AudioObjectGetPropertyDataSize(system, &list, 0, nil, &count)
        guard status == noErr, count.isMultiple(of: unit) else { break }
        if count == 0 { return [] }
        var objects = [AudioObjectID](repeating: kAudioObjectUnknown, count: Int(count / unit))
        let read = objects.withUnsafeMutableBufferPointer { buffer in
            AudioObjectGetPropertyData(system, &list, 0, nil, &count, buffer.baseAddress!)
        }
        if read == noErr { return Array(objects.prefix(Int(count / unit))) }
    }
    throw NSError(domain: "CHIMERA.CoreAudio", code: 1,
                  userInfo: [NSLocalizedDescriptionKey: "Core Audioのプロセス一覧を取得できません"])
}

do {
    let allowed = Set(CommandLine.arguments.dropFirst())
    let observations: [OutputProcess] = try processes().compactMap { object in
        var id: Unmanaged<CFString>?
        guard property(object, kAudioProcessPropertyBundleID, into: &id), let id else { return nil }
        let bundleID = id.takeRetainedValue() as String
        guard allowed.contains(bundleID) else { return nil }
        var pid: pid_t = 0
        var running: UInt32 = 0
        guard property(object, kAudioProcessPropertyPID, into: &pid), pid > 0,
              property(object, kAudioProcessPropertyIsRunningOutput, into: &running) else { return nil }
        return OutputProcess(pid: pid, object: object, bundleID: bundleID, runningOutput: running != 0)
    }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    print(String(decoding: try encoder.encode(observations.sorted { $0.pid < $1.pid }), as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}
