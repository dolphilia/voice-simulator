import CoreAudio
import Darwin
import Foundation

struct TapFailure: LocalizedError {
    let operation: String
    let status: OSStatus

    var errorDescription: String? { "\(operation) に失敗しました (OSStatus \(status))" }
}

func check(_ status: OSStatus, _ operation: String) throws {
    if status != noErr {
        throw TapFailure(operation: operation, status: status)
    }
}

struct AudioBlock: Codable {
    let offset: Int
    let frames: Int
    let sampleTime: Double?
    let hostTime: UInt64?
}

// コールバックでは予約済み領域だけに書き込み、主スレッドは停止後に読み出す。
final class TapBuffer: @unchecked Sendable {
    let pcm: UnsafeMutablePointer<Float>
    let blocks: UnsafeMutablePointer<AudioBlock>
    let capacity: Int
    let blockCapacity: Int
    private(set) var frames = 0
    private(set) var blockCount = 0
    private(set) var overflow = false
    private(set) var formatErrors = 0

    init(capacity: Int, blockCapacity: Int) {
        self.capacity = capacity
        self.blockCapacity = blockCapacity
        pcm = .allocate(capacity: 2 * capacity)
        blocks = .allocate(capacity: blockCapacity)
    }

    deinit {
        blocks.deinitialize(count: blockCount)
        blocks.deallocate()
        pcm.deallocate()
    }

    func append(_ input: UnsafePointer<AudioBufferList>, time: AudioTimeStamp) {
        let buffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
        guard let first = buffers.first, let left = first.mData else { return }
        let width = MemoryLayout<Float>.stride
        let channels = Int(first.mNumberChannels)
        guard (buffers.count == 1 && channels == 2) || (buffers.count == 2 && channels == 1),
              Int(first.mDataByteSize) % (width * channels) == 0 else {
            formatErrors += 1
            return
        }
        let count = Int(first.mDataByteSize) / (width * channels)
        guard count > 0 else { return }
        guard frames + count <= capacity && blockCount < blockCapacity else {
            overflow = true
            return
        }
        let target = pcm + 2 * frames
        if channels == 2 {
            target.initialize(from: left.assumingMemoryBound(to: Float.self), count: 2 * count)
        } else {
            guard buffers[1].mNumberChannels == 1, buffers[1].mDataByteSize == first.mDataByteSize,
                  let right = buffers[1].mData else {
                formatErrors += 1
                return
            }
            let l = left.assumingMemoryBound(to: Float.self)
            let r = right.assumingMemoryBound(to: Float.self)
            for i in 0..<count {
                (target + 2 * i).initialize(to: l[i])
                (target + 2 * i + 1).initialize(to: r[i])
            }
        }
        (blocks + blockCount).initialize(to: AudioBlock(
            offset: frames, frames: count,
            sampleTime: time.mFlags.contains(.sampleTimeValid) ? time.mSampleTime : nil,
            hostTime: time.mFlags.contains(.hostTimeValid) ? time.mHostTime : nil))
        frames += count
        blockCount += 1
    }
}

struct Tape: Codable {
    let pid: pid_t
    let sampleRate: Double
    let frames: Int
    let formatErrors: Int
    let overflow: Bool
    let anchorHostTime: UInt64
    let anchorEpochMs: Double
    let timebaseNumer: UInt32
    let timebaseDenom: UInt32
    let blocks: [AudioBlock]
}

func property(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                               mElement: kAudioObjectPropertyElementMain)
}

func processObject(_ pid: pid_t) throws -> AudioObjectID {
    var pid = pid
    var object = AudioObjectID(kAudioObjectUnknown)
    var address = property(kAudioHardwarePropertyTranslatePIDToProcessObject)
    var size = UInt32(MemoryLayout<AudioObjectID>.size)
    try check(AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address,
                                        UInt32(MemoryLayout<pid_t>.size), &pid, &size, &object), "音声プロセスの照会")
    guard object != kAudioObjectUnknown else {
        throw TapFailure(operation: "音声プロセスの特定", status: kAudioHardwareBadObjectError)
    }
    return object
}

func capture(pid: pid_t, seconds: Double, folder: URL) throws {
    let process = try processObject(pid)
    let description = CATapDescription(stereoMixdownOfProcesses: [process])
    description.name = "CHIMERA PCM Probe"
    description.isPrivate = true
    description.muteBehavior = .unmuted
    var tap = AudioObjectID(kAudioObjectUnknown)
    try check(AudioHardwareCreateProcessTap(description, &tap), "限定したプロセスタップの作成")
    defer { AudioHardwareDestroyProcessTap(tap) }

    var stream = AudioStreamBasicDescription()
    var address = property(kAudioTapPropertyFormat)
    var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
    try check(AudioObjectGetPropertyData(tap, &address, 0, nil, &size, &stream), "タップのPCM形式の取得")
    guard stream.mFormatID == kAudioFormatLinearPCM, stream.mBitsPerChannel == 32,
          stream.mChannelsPerFrame == 2, stream.mFormatFlags & kAudioFormatFlagIsFloat != 0,
          stream.mFormatFlags & kAudioFormatFlagIsBigEndian == 0, stream.mSampleRate > 0 else {
        throw TapFailure(operation: "ステレオFloat32の形式確認", status: kAudioHardwareUnsupportedOperationError)
    }

    let config: [String: Any] = [
        kAudioAggregateDeviceNameKey: "CHIMERA Private PCM Probe",
        kAudioAggregateDeviceUIDKey: UUID().uuidString,
        kAudioAggregateDeviceIsPrivateKey: true,
        kAudioAggregateDeviceTapAutoStartKey: true,
        kAudioAggregateDeviceTapListKey: [[kAudioSubTapUIDKey: description.uuid.uuidString]],
    ]
    var device = AudioObjectID(kAudioObjectUnknown)
    try check(AudioHardwareCreateAggregateDevice(config as CFDictionary, &device), "非公開の採取デバイス作成")
    defer { AudioHardwareDestroyAggregateDevice(device) }
    let buffer = TapBuffer(capacity: Int(stream.mSampleRate * (seconds + 1)), blockCapacity: 8192)
    var handle: AudioDeviceIOProcID?
    try check(AudioDeviceCreateIOProcIDWithBlock(&handle, device, nil) { _, input, time, _, _ in
        buffer.append(input, time: time.pointee)
    }, "採取コールバックの登録")
    guard let handle else {
        throw TapFailure(operation: "採取コールバックの取得", status: kAudioHardwareBadObjectError)
    }
    defer { AudioDeviceDestroyIOProcID(device, handle) }

    let a = mach_absolute_time()
    let epochMs = Date().timeIntervalSince1970 * 1000
    let b = mach_absolute_time()
    var timebase = mach_timebase_info_data_t()
    mach_timebase_info(&timebase)
    FileHandle.standardError.write(Data("AudioDeviceStartを待機します\n".utf8))
    try check(AudioDeviceStart(device, handle), "採取の開始")
    var stopped = false
    defer { if !stopped { AudioDeviceStop(device, handle) } }
    try Data().write(to: folder.appendingPathComponent("tap-ready"), options: .atomic)
    Thread.sleep(forTimeInterval: seconds)
    try check(AudioDeviceStop(device, handle), "採取の停止")
    stopped = true
    let bytes = Data(bytes: buffer.pcm, count: buffer.frames * 2 * MemoryLayout<Float>.stride)
    try bytes.write(to: folder.appendingPathComponent("tap.f32le"))
    let tape = Tape(pid: pid, sampleRate: stream.mSampleRate, frames: buffer.frames,
                    formatErrors: buffer.formatErrors, overflow: buffer.overflow,
                    anchorHostTime: a + (b - a) / 2, anchorEpochMs: epochMs,
                    timebaseNumer: timebase.numer, timebaseDenom: timebase.denom,
                    blocks: Array(UnsafeBufferPointer(start: buffer.blocks, count: buffer.blockCount)))
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(tape).write(to: folder.appendingPathComponent("tap.json"))
}

do {
    let args = CommandLine.arguments
    guard args.count == 4, let pid = pid_t(args[1]), pid > 0,
          let seconds = Double(args[2]), seconds.isFinite, seconds > 0, seconds <= 30 else {
        throw TapFailure(operation: "PID、採取秒数、出力先の指定", status: OSStatus(paramErr))
    }
    let folder = URL(fileURLWithPath: args[3], isDirectory: true)
    try Data(String(getpid()).utf8).write(to: folder.appendingPathComponent("tap-pid"), options: .atomic)
    try capture(pid: pid, seconds: seconds, folder: folder)
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}
