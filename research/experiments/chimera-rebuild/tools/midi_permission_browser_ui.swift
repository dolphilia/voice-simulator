// 専用ChromeプロセスのブラウザUIだけを観測・操作する。
import AppKit
import ApplicationServices
import Foundation

struct Control: Encodable {
    let role: String
    let title: String?
    let description: String?
    let value: String?
    let windowTitle: String?
}

struct WindowInfo: Encodable {
    let id: Int
    let x: Int
    let y: Int
    let width: Int
    let height: Int
}

struct Snapshot: Encodable {
    let pid: Int32
    let frontmost: Bool
    let window: WindowInfo?
    let controls: [Control]
}

func attribute<T>(_ item: AXUIElement, _ key: String) -> T? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(item, key as CFString, &result) == .success else {
        return nil
    }
    return result as? T
}

func controls(_ application: AXUIElement) -> [(Control, AXUIElement)] {
    var found: [(Control, AXUIElement)] = []
    var visited = Set<AXUIElement>()
    func walk(_ item: AXUIElement, depth: Int, window: String?) {
        guard depth < 24, visited.insert(item).inserted else { return }
        let role: String = attribute(item, kAXRoleAttribute) ?? ""
        guard !["AXWebArea", "AXWebView", "AXMenuBar"].contains(role) else { return }
        let title: String? = attribute(item, kAXTitleAttribute)
        let description: String? = attribute(item, kAXDescriptionAttribute)
        let value: String? = role == kAXStaticTextRole ? attribute(item, kAXValueAttribute) : nil
        let windowTitle = role == kAXWindowRole ? title : window
        if title != nil || description != nil || value != nil || ["AXDialog", "AXPopover", "AXSheet"].contains(role) {
            found.append((Control(role: role, title: title, description: description, value: value,
                                  windowTitle: windowTitle), item))
        }
        let children: [AXUIElement] = attribute(item, kAXChildrenAttribute) ?? []
        let sheets: [AXUIElement] = attribute(item, "AXSheets") ?? []
        for child in children + sheets { walk(child, depth: depth + 1, window: windowTitle) }
    }
    let windows: [AXUIElement] = attribute(application, kAXWindowsAttribute) ?? []
    for window in windows { walk(window, depth: 0, window: nil) }
    walk(application, depth: 0, window: nil)
    return found
}

func windowInfo(pid: Int32) -> WindowInfo? {
    let windows = (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
                   as? [[String: Any]]) ?? []
    for window in windows {
        guard window[kCGWindowOwnerPID as String] as? Int32 == pid,
              window[kCGWindowLayer as String] as? Int == 0,
              let id = window[kCGWindowNumber as String] as? Int,
              let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
              let x = bounds["X"], let y = bounds["Y"], let w = bounds["Width"], let h = bounds["Height"],
              w > 200, h > 200 else { continue }
        return WindowInfo(id: id, x: Int(x), y: Int(y), width: Int(w), height: Int(h))
    }
    return nil
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

func buttonCenter(_ item: AXUIElement) -> CGPoint? {
    var position = CGPoint.zero
    var size = CGSize.zero
    guard let pointValue: AXValue = attribute(item, kAXPositionAttribute),
          let sizeValue: AXValue = attribute(item, kAXSizeAttribute),
          AXValueGetValue(pointValue, .cgPoint, &position),
          AXValueGetValue(sizeValue, .cgSize, &size), size.width > 0, size.height > 0 else { return nil }
    return CGPoint(x: position.x + size.width / 2, y: position.y + size.height / 2)
}

let args = CommandLine.arguments
guard args.count >= 3, let pid = Int32(args[1]),
      let running = NSRunningApplication(processIdentifier: pid),
      running.bundleIdentifier == "com.google.Chrome" else {
    fail("専用のGoogle Chromeを起動したPIDが必要です。")
}
guard AXIsProcessTrusted() else { fail("アクセシビリティでブラウザのUIを読めません。") }

let app = AXUIElementCreateApplication(pid)
if args[2] == "activate" {
    guard running.activate() else { fail("専用Chromeを手前に出せません。") }
} else if args[2] == "snapshot" {
    let data = Snapshot(pid: pid, frontmost: NSWorkspace.shared.frontmostApplication?.processIdentifier == pid,
                        window: windowInfo(pid: pid), controls: controls(app).map { $0.0 })
    try FileHandle.standardOutput.write(contentsOf: JSONEncoder().encode(data))
} else if args[2] == "press" {
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid else {
        fail("専用Chromeが手前にある場合に操作できます。")
    }
    guard args.count == 5 else { fail("観測したサイトとボタンを指定してください。") }
    let matches = controls(app).filter { control, _ in
        control.role == kAXButtonRole && [control.title, control.description, control.value].contains(args[4])
            && control.windowTitle?.contains(args[3]) == true && control.windowTitle?.contains("MIDI") == true
    }
    guard matches.count == 1, let item = matches.first?.1, let point = buttonCenter(item), let window = windowInfo(pid: pid),
          CGRect(x: window.x, y: window.y, width: window.width, height: window.height).contains(point) else {
        fail("観測したボタンと現在のブラウザUIが一致しません。")
    }
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid else {
        fail("操作の直前に別のアプリが手前になりました。")
    }
    for type in [CGEventType.leftMouseDown, .leftMouseUp] {
        guard let event = CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: point, mouseButton: .left)
        else { fail("ブラウザのクリックを作成できません。") }
        event.post(tap: .cghidEventTap)
    }
} else {
    fail("専用Chromeの操作を認識できません。")
}
