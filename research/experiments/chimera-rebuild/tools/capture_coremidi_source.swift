import CoreMIDI
import Darwin
import Foundation

struct ProbeError: Error {
    let operation: String
    let status: OSStatus
}

func check(_ status: OSStatus, _ operation: String) throws {
    if status != 0 { throw ProbeError(operation: operation, status: status) }
}

func report(_ row: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
    FileHandle.standardOutput.write(data + Data([10]))
}

func isListed(_ source: MIDIEndpointRef) -> Bool {
    (0..<MIDIGetNumberOfSources()).contains { MIDIGetSource($0) == source }
}

func send(_ bytes: [UInt8], group: UInt8, through source: MIDIEndpointRef) throws {
    // UMPの種別2はMIDI 1.0のチャンネルメッセージを1語に格納する。
    var word = (UInt32(2) << 28) | (UInt32(group) << 24) | (UInt32(bytes[0]) << 16)
        | (UInt32(bytes[1]) << 8) | UInt32(bytes[2])
    let events = UnsafeMutablePointer<MIDIEventList>.allocate(capacity: 1)
    defer { events.deallocate() }
    let first = MIDIEventListInit(events, ._1_0)
    let timestamp = mach_absolute_time()
    MIDIEventListAdd(events, MemoryLayout<MIDIEventList>.size, first, timestamp, 1, &word)
    guard events.pointee.numPackets == 1 else {
        throw ProbeError(operation: "MIDIEventListAdd", status: -1)
    }
    let before = DispatchTime.now().uptimeNanoseconds
    try check(MIDIReceivedEventList(source, events), "MIDIReceivedEventList")
    let after = DispatchTime.now().uptimeNanoseconds
    try report(["action": "send", "bytes": bytes, "word": word,
                "timestampHostTicks": String(timestamp),
                "beforeUptimeNs": String(before), "afterUptimeNs": String(after)])
}

func run() throws {
    let args = CommandLine.arguments
    guard args.count == 3, let group = UInt8(args[2]), group < 16 else {
        throw ProbeError(operation: "送信元名と0〜15のグループ番号が必要です", status: -1)
    }
    var client: MIDIClientRef = 0
    try check(MIDIClientCreateWithBlock("CHIMERA研究計測" as CFString, &client, nil), "MIDIClientCreateWithBlock")
    defer { MIDIClientDispose(client) }
    var source: MIDIEndpointRef = 0
    try check(MIDISourceCreateWithProtocol(client, args[1] as CFString, ._1_0, &source), "MIDISourceCreateWithProtocol")
    let endpoint = source
    defer { if source != 0 { MIDIEndpointDispose(source) } }
    try report(["action": "add", "name": args[1], "endpoint": endpoint, "listed": isListed(endpoint)])
    while let line = readLine(), line != "remove" {
        let bytes = line.split(separator: " ").compactMap { UInt8($0) }
        guard bytes.count == 3, [0x80, 0x90].contains(bytes[0] & 0xf0), bytes[1...].allSatisfy({ $0 < 128 }) else {
            throw ProbeError(operation: "ノート操作の3バイトが必要です", status: -1)
        }
        try send(bytes, group: group, through: endpoint)
    }
    let before = DispatchTime.now().uptimeNanoseconds
    try check(MIDIEndpointDispose(source), "MIDIEndpointDispose")
    let after = DispatchTime.now().uptimeNanoseconds
    source = 0
    try report(["action": "remove", "endpoint": endpoint, "listed": isListed(endpoint),
                "beforeUptimeNs": String(before), "afterUptimeNs": String(after)])
}

func observeRemoval(of endpoint: MIDIEndpointRef) throws {
    guard isListed(endpoint) else { throw ProbeError(operation: "観測する送信元が見つかりません", status: -1) }
    var client: MIDIClientRef = 0
    let filter = UnsafeMutablePointer<MIDIEndpointRef>.allocate(capacity: 1)
    filter.initialize(to: endpoint)
    defer { filter.deallocate() }
    try check(MIDIClientCreate("CHIMERA研究計測通知" as CFString, { message, context in
        guard let context, message.pointee.messageID == .msgObjectRemoved else { return }
        let notification = message.withMemoryRebound(to: MIDIObjectAddRemoveNotification.self, capacity: 1) { $0.pointee }
        let expected = context.assumingMemoryBound(to: MIDIEndpointRef.self).pointee
        guard notification.child == expected, notification.childType == .source else { return }
        let notified = DispatchTime.now().uptimeNanoseconds
        try? report(["action": "notified", "endpoint": expected, "uptimeNs": String(notified)])
        CFRunLoopStop(CFRunLoopGetCurrent())
    }, filter, &client), "MIDIClientCreate")
    defer { MIDIClientDispose(client) }
    try report(["action": "watching", "endpoint": endpoint])
    CFRunLoopRun()
}

func property(_ object: MIDIObjectRef, _ key: CFString) -> String {
    var value: Unmanaged<CFString>?
    guard object != 0, MIDIObjectGetStringProperty(object, key, &value) == 0,
          let value else { return "" }
    return value.takeRetainedValue() as String
}

func listInputs() throws {
    for index in 0..<MIDIGetNumberOfSources() {
        let endpoint = MIDIGetSource(index)
        var uid: Int32 = 0
        var entity: MIDIEntityRef = 0
        var device: MIDIDeviceRef = 0
        try check(MIDIObjectGetIntegerProperty(endpoint, kMIDIPropertyUniqueID, &uid), "MIDI入力の固有ID")
        _ = MIDIEndpointGetEntity(endpoint, &entity)
        if entity != 0 { _ = MIDIEntityGetDevice(entity, &device) }
        try report(["uid": uid, "endpoint": endpoint, "entity": entity, "device": device,
                    "name": property(endpoint, kMIDIPropertyName),
                    "displayName": property(endpoint, kMIDIPropertyDisplayName),
                    "manufacturer": property(device, kMIDIPropertyManufacturer),
                    "model": property(device, kMIDIPropertyModel),
                    "driver": property(device, kMIDIPropertyDriverOwner)])
    }
}

let noteReports = DispatchQueue(label: "chimera.midi.receive-notes")

func observeNotes(from endpoint: MIDIEndpointRef) throws {
    guard isListed(endpoint) else { throw ProbeError(operation: "観測する入力が見つかりません", status: -1) }
    var client: MIDIClientRef = 0
    try check(MIDIClientCreateWithBlock("CHIMERA MIDI受信" as CFString, &client, nil), "MIDIClientCreateWithBlock")
    defer { MIDIClientDispose(client) }
    var port: MIDIPortRef = 0
    try check(MIDIInputPortCreateWithProtocol(client, "ノートの受動観測" as CFString, ._1_0, &port) { list, _ in
        MIDIEventListForEachEvent(list, { _, timeStamp, message in
            guard message.type.rawValue == 2 else { return }
            let event = message.channelVoice1
            let status = event.status.rawValue
            guard status == 8 || status == 9 else { return }
            let bytes = [UInt8(status << 4) | event.channel, event.note.number, event.note.velocity]
            let arrival = DispatchTime.now().uptimeNanoseconds
            noteReports.async {
                try? report(["action": "note", "bytes": bytes, "group": message.group,
                             "timestampHostTicks": String(timeStamp), "arrivalUptimeNs": String(arrival)])
            }
        }, nil)
    }, "MIDIInputPortCreateWithProtocol")
    defer { MIDIPortDispose(port) }
    try check(MIDIPortConnectSource(port, endpoint, nil), "MIDIPortConnectSource")
    try report(["action": "listening", "endpoint": endpoint])
    while let line = readLine(), line != "stop" {}
    try check(MIDIPortDisconnectSource(port, endpoint), "MIDIPortDisconnectSource")
    noteReports.sync {}
}

do {
    let args = CommandLine.arguments
    if args.count == 2 && args[1] == "--list-inputs" {
        try listInputs()
    } else if args.count == 3 && args[1] == "--listen-notes", let endpoint = MIDIEndpointRef(args[2]) {
        try observeNotes(from: endpoint)
    } else if args.count == 3 && args[1] == "--watch-removal", let endpoint = MIDIEndpointRef(args[2]) {
        try observeRemoval(of: endpoint)
    } else {
        try run()
    }
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(1)
}
