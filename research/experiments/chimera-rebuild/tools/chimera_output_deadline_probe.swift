import AudioToolbox
import Darwin
import Dispatch
import Foundation

struct OutputMark: Codable {
    let frames: UInt32
    let markerOffset: Int
    let hostTime: UInt64?
    let sampleTime: Double?
    let entered: UInt64
    let emitted: UInt64
    let status: OSStatus?
    let bufferEntry: OutputBufferEntry?
}

struct OutputBufferEntry: Codable {
    let zeroSamples: Int
    let previousMarkerOffset: Int?
    let sameBufferAsPrevious: Bool
    let action: String
}

struct OutputPCMSettings: Decodable {
    enum EntryMode: String, Decodable {
        case retain, zero
    }

    let markerPath: String
    let pcmPath: String
    let eventCallbacks: Int
    let entryMode: EntryMode?
    let entryNeighbors: Int?
    let entryLookback: Int?
    let restart: OutputRestartSettings?
}

struct OutputRestartSettings: Decodable {
    let stopAfterFrame: Int
    let resumeSourceFrame: Int
    let pauseSeconds: Double
}

struct OutputRestartRecord: Codable {
    let recordedFramesAtStop: Int
    let recordedBlocksAtStop: Int
    let resumeSourceFrame: Int
    let stopRequestedHostTicks: UInt64
    let stopReturnedHostTicks: UInt64
    let startRequestedHostTicks: UInt64
    let startReturnedHostTicks: UInt64
}

final class OutputPCM {
    let settings: OutputPCMSettings
    let marker: [Float]
    let capacity: Int
    let recorded: UnsafeMutablePointer<Float>
    var written = 0
    var sourceAdvance = 0
    private var last: Float = 0
    private var previousBuffer: UnsafeMutablePointer<Float>?

    init(settings: OutputPCMSettings, capacity: Int) throws {
        let bytes = try Data(contentsOf: URL(fileURLWithPath: settings.markerPath))
        let width = MemoryLayout<UInt32>.size
        guard !bytes.isEmpty, bytes.count.isMultiple(of: width), (1...2048).contains(settings.eventCallbacks),
              (0...2048).contains(settings.entryNeighbors ?? 0), (0...2048).contains(settings.entryLookback ?? 0) else {
            throw OutputError(stage: "出力PCM対照の設定確認", status: kAudioUnitErr_InvalidParameter)
        }
        marker = bytes.withUnsafeBytes { buffer in
            stride(from: 0, to: buffer.count, by: width).map { offset in
                Float(bitPattern: UInt32(littleEndian: buffer.loadUnaligned(fromByteOffset: offset, as: UInt32.self)))
            }
        }
        self.settings = settings
        self.capacity = capacity
        recorded = .allocate(capacity: capacity * 2)
    }

    deinit {
        recorded.deinitialize(count: written * 2)
        recorded.deallocate()
    }

    private func observeEntry(_ target: UnsafeMutablePointer<Float>, count: Int,
                              mode: OutputPCMSettings.EntryMode, duringEvent: Bool) -> OutputBufferEntry {
        let samples = count * 2
        let raw = UnsafeRawPointer(target)
        let width = MemoryLayout<UInt32>.size
        var zeroSamples = 0
        for i in 0..<samples {
            let bits = raw.loadUnaligned(fromByteOffset: i * width, as: UInt32.self)
            if bits & 0x7fffffff == 0 { zeroSamples += 1 }
        }
        var previousOffset: Int?
        if zeroSamples != samples {
            let lookback = min(settings.entryLookback ?? 0, written / count)
            for k in 0..<lookback {
                let offset = written - (k + 1) * count
                if memcmp(target, recorded + offset * 2, samples * width) == 0 {
                    previousOffset = offset
                    break
                }
            }
        }
        let action: String
        if !duringEvent {
            action = "marker"
        } else if mode == .zero {
            action = "explicit_zero"
        } else if zeroSamples == samples || previousOffset != nil {
            action = "retain"
        } else {
            // 由来を確認できない内容は採取や出力に使わない。
            action = "fallback_zero"
        }
        return OutputBufferEntry(zeroSamples: zeroSamples, previousMarkerOffset: previousOffset,
                                 sameBufferAsPrevious: previousBuffer == target, action: action)
    }

    func write(_ target: UnsafeMutablePointer<Float>, count: Int, callback: Int, event: Int) -> OutputBufferEntry? {
        let duringEvent = callback >= event && callback - event < settings.eventCallbacks
        let entry: OutputBufferEntry?
        let neighbors = settings.entryNeighbors ?? 0
        if let mode = settings.entryMode, (event - neighbors)..<(event + settings.eventCallbacks + neighbors) ~= callback {
            entry = observeEntry(target, count: count, mode: mode, duringEvent: duringEvent)
        } else {
            entry = nil
        }
        if settings.entryMode != nil && duringEvent {
            if entry?.action != "retain" {
                for i in 0..<(count * 2) { target[i] = 0 }
            }
        } else {
            let startingFade = callback == event
            let step = startingFade ? last / Float(count) : 0
            for i in 0..<count {
                if startingFade {
                    last -= step
                } else {
                    last = duringEvent ? 0 : marker[(written + sourceAdvance + i) % marker.count]
                }
                target[2 * i] = last
                target[2 * i + 1] = -last
            }
        }
        previousBuffer = target
        (recorded + written * 2).initialize(from: target, count: count * 2)
        written += count
        return entry
    }

    func save() throws {
        let bytes = Data(bytes: recorded, count: written * 2 * MemoryLayout<Float>.size)
        try bytes.write(to: URL(fileURLWithPath: settings.pcmPath))
    }
}

final class OutputProbe {
    let delayTicks: UInt64
    let overrunIndex: Int
    let failureCount: Int?
    let pcm: OutputPCM?
    let stopReady: DispatchSemaphore?
    let marks = UnsafeMutablePointer<OutputMark>.allocate(capacity: 2048)
    var count = 0
    var frames = 0
    var invalidBuffers = 0

    init(index: Int, delayTicks: UInt64, failureCount: Int?, pcm: OutputPCM?) {
        overrunIndex = index
        self.delayTicks = delayTicks
        self.failureCount = failureCount
        self.pcm = pcm
        self.stopReady = pcm?.settings.restart.map { _ in DispatchSemaphore(value: 0) }
    }

    deinit {
        marks.deinitialize(count: count)
        marks.deallocate()
    }

    func write(_ data: UnsafeMutablePointer<AudioBufferList>, frames n: UInt32,
               time: AudioTimeStamp) -> OSStatus {
        let entered = mach_absolute_time()
        let list = UnsafeMutableAudioBufferListPointer(data)
        let count = Int(n)
        guard list.count == 1, list[0].mNumberChannels == 2,
              list[0].mDataByteSize >= count * 2 * MemoryLayout<Float>.stride,
              let target = list[0].mData?.assumingMemoryBound(to: Float.self) else {
            invalidBuffers += 1
            return kAudioUnitErr_FormatNotSupported
        }
        if delayTicks > 0 && self.count == overrunIndex {
            let finish = entered + delayTicks
            while mach_absolute_time() < finish {}
        }
        let bufferEntry: OutputBufferEntry?
        if let pcm {
            guard count > 0, pcm.written + count <= pcm.capacity else {
                invalidBuffers += 1
                return kAudioUnitErr_TooManyFramesToProcess
            }
            bufferEntry = pcm.write(target, count: count, callback: self.count, event: overrunIndex)
        } else {
            for i in 0..<count {
                let sample = Float(((frames + i) * 421 + 173) % 65_521 - 32_760) / 8_388_608
                target[2 * i] = sample
                target[2 * i + 1] = -sample
            }
            bufferEntry = nil
        }
        let status: OSStatus = (overrunIndex..<(overrunIndex + (failureCount ?? 0))).contains(self.count) ? -1 : noErr
        if self.count < 2048 {
            (marks + self.count).initialize(to: OutputMark(
                frames: n, markerOffset: frames,
                hostTime: time.mFlags.contains(.hostTimeValid) ? time.mHostTime : nil,
                sampleTime: time.mFlags.contains(.sampleTimeValid) ? time.mSampleTime : nil,
                entered: entered, emitted: mach_absolute_time(), status: failureCount.map { _ in status },
                bufferEntry: bufferEntry))
            self.count += 1
        }
        frames += count
        if let targetFrame = pcm?.settings.restart?.stopAfterFrame, frames - count < targetFrame && targetFrame <= frames {
            stopReady?.signal()
        }
        return status
    }
}

struct OutputClock: Codable {
    let hostTicks: UInt64
    let epochNs: UInt64
    let bracketsTicks: UInt64

    init() {
        let before = mach_absolute_time()
        let epochNs = clock_gettime_nsec_np(CLOCK_REALTIME)
        let after = mach_absolute_time()
        hostTicks = before + (after - before) / 2
        self.epochNs = epochNs
        bracketsTicks = after - before
    }
}

struct OutputRecord: Codable {
    let sampleRate: Double
    let timebaseNumer: UInt32
    let timebaseDenom: UInt32
    let delayMs: Double
    let invalidBuffers: Int
    let frameMarks: [OutputMark]
    let clock: OutputClock?
    let pid: Int32?
    let restart: OutputRestartRecord?
}

struct OutputError: LocalizedError {
    let stage: String
    let status: OSStatus
    var errorDescription: String? { "\(stage) に失敗しました (OSStatus \(status))" }
}

func check(_ status: OSStatus, _ stage: String) throws {
    if status != noErr {
        throw OutputError(stage: stage, status: status)
    }
}

func run(index: Int, delayMs: Double, rate: Double, seconds: Double, failureCount: Int?,
         readyFile: URL?, pcmSettings: OutputPCMSettings?) throws -> OutputRecord {
    var descriptor = AudioComponentDescription(componentType: kAudioUnitType_Output,
        componentSubType: kAudioUnitSubType_DefaultOutput, componentManufacturer: kAudioUnitManufacturer_Apple,
        componentFlags: 0, componentFlagsMask: 0)
    guard let component = AudioComponentFindNext(nil, &descriptor) else {
        throw OutputError(stage: "出力AudioUnitの取得", status: kAudioUnitErr_InvalidProperty)
    }
    var instance: AudioComponentInstance?
    try check(AudioComponentInstanceNew(component, &instance), "AudioUnitの作成")
    guard let unit = instance else {
        throw OutputError(stage: "AudioUnitの取得", status: kAudioUnitErr_Uninitialized)
    }
    defer { AudioComponentInstanceDispose(unit) }
    var format = AudioStreamBasicDescription(mSampleRate: rate, mFormatID: kAudioFormatLinearPCM,
        mFormatFlags: kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked,
        mBytesPerPacket: 8, mFramesPerPacket: 1, mBytesPerFrame: 8, mChannelsPerFrame: 2,
        mBitsPerChannel: 32, mReserved: 0)
    try check(AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0,
                                   &format, UInt32(MemoryLayout.size(ofValue: format))), "出力形式の設定")
    var timebase = mach_timebase_info_data_t()
    mach_timebase_info(&timebase)
    let delayTicks = UInt64(delayMs * 1_000_000 * Double(timebase.denom) / Double(timebase.numer))
    let pcm = try pcmSettings.map { try OutputPCM(settings: $0, capacity: Int(rate * (seconds + 1))) }
    let probe = OutputProbe(index: index, delayTicks: delayTicks, failureCount: failureCount, pcm: pcm)
    var render = AURenderCallbackStruct(inputProc: { ref, _, time, _, frames, data in
        guard let data else { return kAudioUnitErr_InvalidParameter }
        return Unmanaged<OutputProbe>.fromOpaque(ref).takeUnretainedValue().write(data, frames: frames, time: time.pointee)
    }, inputProcRefCon: Unmanaged.passUnretained(probe).toOpaque())
    try check(AudioUnitSetProperty(unit, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0,
                                   &render, UInt32(MemoryLayout.size(ofValue: render))), "描画コールバックの設定")
    try check(AudioUnitInitialize(unit), "AudioUnitの初期化")
    defer { AudioUnitUninitialize(unit) }
    if let readyFile {
        try Data().write(to: readyFile, options: .atomic)
        guard FileHandle.standardInput.readData(ofLength: 1) == Data([1]) else {
            throw OutputError(stage: "トレース開始通知の受け取り", status: kAudioUnitErr_CannotDoInCurrentContext)
        }
    }
    let clock = failureCount.map { _ in OutputClock() }
    try check(AudioOutputUnitStart(unit), "再生の開始")
    let restartRecord: OutputRestartRecord?
    if let pcm, let restart = pcm.settings.restart, let ready = probe.stopReady {
        guard ready.wait(timeout: .now() + Double(restart.stopAfterFrame) / rate + 2) == .success else {
            try check(AudioOutputUnitStop(unit), "停止準備の待機を中断")
            try pcm.save()
            throw OutputError(stage: "停止フレームの通知", status: kAudioUnitErr_CannotDoInCurrentContext)
        }
        let stopRequested = mach_absolute_time()
        try check(AudioOutputUnitStop(unit), "途中での停止")
        let stopReturned = mach_absolute_time()
        let stoppedFrames = probe.frames
        let stoppedBlocks = probe.count
        guard stoppedFrames <= restart.resumeSourceFrame else {
            try pcm.save()
            throw OutputError(stage: "停止時の出力フレームの確認", status: kAudioUnitErr_InvalidParameter)
        }
        pcm.sourceAdvance = restart.resumeSourceFrame - stoppedFrames
        Thread.sleep(forTimeInterval: restart.pauseSeconds)
        let startRequested = mach_absolute_time()
        try check(AudioOutputUnitStart(unit), "途中停止からの再開")
        let startReturned = mach_absolute_time()
        restartRecord = OutputRestartRecord(recordedFramesAtStop: stoppedFrames, recordedBlocksAtStop: stoppedBlocks,
                                            resumeSourceFrame: restart.resumeSourceFrame, stopRequestedHostTicks: stopRequested,
                                            stopReturnedHostTicks: stopReturned, startRequestedHostTicks: startRequested,
                                            startReturnedHostTicks: startReturned)
        Thread.sleep(forTimeInterval: seconds - Double(restart.resumeSourceFrame) / rate)
    } else {
        Thread.sleep(forTimeInterval: seconds)
        restartRecord = nil
    }
    try check(AudioOutputUnitStop(unit), "再生の停止")
    try pcm?.save()
    return OutputRecord(sampleRate: rate, timebaseNumer: timebase.numer, timebaseDenom: timebase.denom,
                        delayMs: delayMs, invalidBuffers: probe.invalidBuffers,
                        frameMarks: Array(UnsafeBufferPointer(start: probe.marks, count: probe.count)),
                        clock: clock, pid: failureCount.map { _ in getpid() }, restart: restartRecord)
}

do {
    let args = CommandLine.arguments
    guard (5...8).contains(args.count), let index = Int(args[1]), index >= 0,
          let delay = Double(args[2]), delay.isFinite, (0...20).contains(delay),
          let rate = Double(args[3]), rate == 48_000 || rate == 44_100,
          let seconds = Double(args[4]), seconds.isFinite, (0.5...12).contains(seconds) else {
        throw OutputError(stage: "計測引数の確認", status: kAudioUnitErr_InvalidParameter)
    }
    let failureCount: Int?
    if args.count >= 6 {
        guard let count = Int(args[5]), delay == 0, (0...2047).contains(index), (0...(2048 - index)).contains(count) else {
            throw OutputError(stage: "戻り値を変更する要求範囲の確認", status: kAudioUnitErr_InvalidParameter)
        }
        failureCount = count
    } else {
        failureCount = nil
    }
    let readyFile = args.count >= 7 ? URL(fileURLWithPath: args[6]) : nil
    let pcmSettings = args.count == 8
        ? try JSONDecoder().decode(OutputPCMSettings.self, from: Data(contentsOf: URL(fileURLWithPath: args[7])))
        : nil
    guard seconds <= 3 || (rate == 44_100 && index == 2047 && failureCount == 0
                          && pcmSettings != nil && pcmSettings?.entryMode == nil) else {
        throw OutputError(stage: "長時間の44.1 kHz PCM対照の引数確認", status: kAudioUnitErr_InvalidParameter)
    }
    if let restart = pcmSettings?.restart {
        guard seconds > 3, restart.stopAfterFrame > 0, restart.stopAfterFrame < restart.resumeSourceFrame,
              restart.resumeSourceFrame < Int(seconds * rate), (0.1...2).contains(restart.pauseSeconds) else {
            throw OutputError(stage: "途中停止の計測条件の確認", status: kAudioUnitErr_InvalidParameter)
        }
    }
    let eventIndex = seconds > 3 ? Int.max / 2 : index
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let record = try run(index: eventIndex, delayMs: delay, rate: rate, seconds: seconds, failureCount: failureCount,
                         readyFile: readyFile, pcmSettings: pcmSettings)
    try FileHandle.standardOutput.write(contentsOf: encoder.encode(record))
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}
