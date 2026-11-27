import CoreAudio
import Darwin
import Foundation

let system = AudioObjectID(kAudioObjectSystemObject)

struct Device: Encodable {
    let id: AudioObjectID
    let name: String
    let uid: String
    let sampleRate: Double
    let bufferFrames: UInt32
}

struct Snapshot: Encodable {
    let defaultOutput: AudioObjectID
    let devices: [Device]
}

func failure(_ operation: String, _ status: OSStatus) -> NSError {
    NSError(domain: "CHIMERA.CoreAudio", code: Int(status),
            userInfo: [NSLocalizedDescriptionKey: "\(operation)に失敗しました (OSStatus \(status))"])
}

func address(_ selector: AudioObjectPropertySelector,
             scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
}

func property<T>(_ device: AudioObjectID, _ selector: AudioObjectPropertySelector, _ initial: T,
                 scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) throws -> T {
    var attr = address(selector, scope: scope)
    var size = UInt32(MemoryLayout<T>.size)
    var value = initial
    let status = withUnsafeMutablePointer(to: &value) {
        AudioObjectGetPropertyData(device, &attr, 0, nil, &size, $0)
    }
    guard status == noErr else { throw failure("音声機器の属性 \(selector) の取得", status) }
    return value
}

func deviceIDs() throws -> [AudioObjectID] {
    var attr = address(kAudioHardwarePropertyDevices)
    var size: UInt32 = 0
    let queried = AudioObjectGetPropertyDataSize(system, &attr, 0, nil, &size)
    guard queried == noErr else { throw failure("音声機器一覧のサイズ取得", queried) }
    let width = UInt32(MemoryLayout<AudioObjectID>.stride)
    guard size > 0, size.isMultiple(of: width) else { return [] }
    var devices = [AudioObjectID](repeating: kAudioObjectUnknown, count: Int(size / width))
    let read = devices.withUnsafeMutableBytes {
        AudioObjectGetPropertyData(system, &attr, 0, nil, &size, $0.baseAddress!)
    }
    guard read == noErr else { throw failure("音声機器一覧の取得", read) }
    return Array(devices.prefix(Int(size / width)))
}

func snapshot() throws -> Snapshot {
    let current = try property(system, kAudioHardwarePropertyDefaultOutputDevice, AudioObjectID(0))
    let devices: [Device] = try deviceIDs().compactMap { id in
        guard (try? property(id, kAudioDevicePropertyDeviceCanBeDefaultDevice, UInt32(0),
                             scope: kAudioDevicePropertyScopeOutput)) == 1 || id == current else { return nil }
        let name = try property(id, kAudioObjectPropertyName, nil as Unmanaged<CFString>?)
        let uid = try property(id, kAudioDevicePropertyDeviceUID, nil as Unmanaged<CFString>?)
        guard let name, let uid else { return nil }
        return try Device(id: id, name: name.takeRetainedValue() as String, uid: uid.takeRetainedValue() as String,
                          sampleRate: property(id, kAudioDevicePropertyNominalSampleRate, 0.0),
                          bufferFrames: property(id, kAudioDevicePropertyBufferFrameSize, UInt32(0)))
    }
    return Snapshot(defaultOutput: current, devices: devices.sorted { $0.id < $1.id })
}

do {
    let args = Array(CommandLine.arguments.dropFirst())
    if args.count == 3, args[0] == "select", let expected = AudioObjectID(args[1]),
       var target = AudioObjectID(args[2]) {
        let before = try snapshot()
        guard before.defaultOutput == expected, before.devices.contains(where: { $0.id == target }) else {
            throw failure("選択前の既定出力と対象機器の確認", kAudioHardwareBadDeviceError)
        }
        var attr = address(kAudioHardwarePropertyDefaultOutputDevice)
        let status = AudioObjectSetPropertyData(system, &attr, 0, nil,
                                               UInt32(MemoryLayout<AudioObjectID>.size), &target)
        guard status == noErr else { throw failure("既定の音声出力の選択", status) }
    } else if !args.isEmpty {
        throw failure("照会または select 現在の機器ID 選択する機器ID の指定", OSStatus(paramErr))
    }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    print(String(decoding: try encoder.encode(snapshot()), as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}
