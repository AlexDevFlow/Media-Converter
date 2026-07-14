// FileConverterUI — native SwiftUI front-end for File Converter on macOS.
//
// Compiled at install time by `fileconverter --install` (swiftc from the
// Xcode Command Line Tools). This binary is a *dumb renderer*: every piece
// of logic — conversions, ETA math, auto-close timing, i18n — lives in the
// Python process, which drives this UI over a JSON-lines protocol:
//
//   python → stdin : {"type":"init"|"update"|"summary"|"saved"|"exit", ...}
//   stdout → python: {"ready":true} | {"cancel":N} | {"keep_open":true}
//                    | {"preset":"To Mp4"} | {"action":"save",...}
//                    | {"closed":true}
//
// Modes (argv[1]): progress | pick | settings

import AppKit
import Foundation
import SwiftUI

// MARK: - IO

enum IO {
    private static let lock = NSLock()

    static func send(_ obj: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(obj),
              var data = try? JSONSerialization.data(withJSONObject: obj) else { return }
        data.append(0x0a)
        lock.lock()
        defer { lock.unlock() }
        // Raw write(2): with SIGPIPE ignored this fails silently if Python
        // is gone, instead of raising an uncatchable NSException.
        data.withUnsafeBytes { buf in
            var off = 0
            while off < buf.count {
                let n = write(1, buf.baseAddress!.advanced(by: off), buf.count - off)
                if n <= 0 { break }
                off += n
            }
        }
    }

    static func readLoop(_ handler: @escaping ([String: Any]) -> Void) {
        Thread.detachNewThread {
            while let line = readLine(strippingNewline: true) {
                guard !line.isEmpty,
                      let data = line.data(using: .utf8),
                      let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                else { continue }
                DispatchQueue.main.async { handler(obj) }
            }
            // stdin EOF — the Python side is gone; quit quietly.
            DispatchQueue.main.async {
                WindowRunner.shared.suppressCloseMessage = true
                NSApp.terminate(nil)
            }
        }
    }
}

// MARK: - Window bootstrap

final class WindowRunner: NSObject, NSApplicationDelegate, NSWindowDelegate {
    static let shared = WindowRunner()
    var window: NSWindow?
    var suppressCloseMessage = false

    func run<V: View>(title: String, width: CGFloat, height: CGFloat,
                      minW: CGFloat, minH: CGFloat, view: V) {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        app.delegate = self

        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: height),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false)
        win.title = title
        win.minSize = NSSize(width: minW, height: minH)
        win.isReleasedWhenClosed = false
        win.contentView = NSHostingView(rootView: view)
        win.center()
        win.delegate = self
        win.makeKeyAndOrderFront(nil)
        window = win

        app.activate(ignoringOtherApps: true)
        app.run()
    }

    func setTitle(_ title: String) { window?.title = title }

    func windowWillClose(_ notification: Notification) {
        if !suppressCloseMessage {
            suppressCloseMessage = true
            IO.send(["closed": true])
        }
        NSApp.terminate(nil)
    }
}

func str(_ table: [String: String], _ key: String, _ fallback: String) -> String {
    table[key] ?? fallback
}

// MARK: - Progress mode

final class JobVM: ObservableObject, Identifiable {
    let id: Int
    let name: String
    let out: String
    @Published var progress: Double = 0
    @Published var progressText = ""
    @Published var status = ""
    @Published var state = "ready"
    @Published var cancelling = false

    init(id: Int, name: String, out: String) {
        self.id = id
        self.name = name
        self.out = out
    }
}

final class ProgressVM: ObservableObject {
    @Published var jobs: [JobVM] = []
    @Published var summary = ""
    @Published var showKeepOpen = false
    @Published var strings: [String: String] = [:]

    func handle(_ msg: [String: Any]) {
        switch msg["type"] as? String {
        case "init":
            strings = msg["strings"] as? [String: String] ?? [:]
            if let title = msg["title"] as? String { WindowRunner.shared.setTitle(title) }
            jobs = (msg["jobs"] as? [[String: Any]] ?? []).map { j in
                let vm = JobVM(id: j["id"] as? Int ?? 0,
                               name: j["name"] as? String ?? "?",
                               out: j["out"] as? String ?? "")
                vm.status = str(strings, "waiting", "Waiting...")
                return vm
            }
            IO.send(["ready": true])
        case "update":
            guard let id = msg["id"] as? Int,
                  let job = jobs.first(where: { $0.id == id }) else { return }
            if let v = msg["progress"] as? Double { job.progress = v }
            if let v = msg["state"] as? String { job.state = v }
            if let v = msg["progress_text"] as? String { job.progressText = v }
            if let v = msg["status"] as? String { job.status = v }
        case "summary":
            summary = msg["text"] as? String ?? ""
            showKeepOpen = msg["show_keep_open"] as? Bool ?? false
        case "exit":
            WindowRunner.shared.suppressCloseMessage = true
            NSApp.terminate(nil)
        default:
            break
        }
    }
}

struct JobRowView: View {
    @ObservedObject var job: JobVM
    let strings: [String: String]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(job.name)
                    .fontWeight(.semibold)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                Text("→ \(job.out)").foregroundColor(.secondary)
                if job.state == "ready" || job.state == "in_progress" || job.state == "unknown" {
                    Button(job.cancelling ? str(strings, "cancelling", "Cancelling...")
                                          : str(strings, "cancel", "Cancel")) {
                        job.cancelling = true
                        IO.send(["cancel": job.id])
                    }
                    .disabled(job.cancelling)
                }
            }
            HStack(spacing: 8) {
                ProgressView(value: min(max(job.progress, 0), 1))
                    .progressViewStyle(.linear)
                Text(job.progressText)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(minWidth: 140, alignment: .trailing)
            }
            Text(job.status)
                .font(.caption)
                .foregroundColor(job.state == "failed" ? .red : .secondary)
                .lineLimit(2)
            Divider()
        }
    }
}

struct ProgressWindowView: View {
    @ObservedObject var model: ProgressVM

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(model.jobs) { job in
                        JobRowView(job: job, strings: model.strings)
                    }
                }
                .padding(12)
            }
            Divider()
            HStack {
                Text(model.summary).font(.callout)
                Spacer()
                if model.showKeepOpen {
                    Button(str(model.strings, "keep_open", "Keep open")) {
                        IO.send(["keep_open": true])
                    }
                }
            }
            .padding(10)
        }
        .frame(minWidth: 480, minHeight: 240)
    }
}

// MARK: - Pick mode

struct PickPreset: Identifiable {
    let id: String
    let short: String
    let folder: String
    let out: String
}

final class PickVM: ObservableObject {
    @Published var presets: [PickPreset] = []
    @Published var info = ""
    @Published var strings: [String: String] = [:]

    func handle(_ msg: [String: Any]) {
        switch msg["type"] as? String {
        case "init":
            strings = msg["strings"] as? [String: String] ?? [:]
            if let title = msg["title"] as? String { WindowRunner.shared.setTitle(title) }
            info = msg["info"] as? String ?? ""
            presets = (msg["presets"] as? [[String: Any]] ?? []).map { p in
                PickPreset(id: p["name"] as? String ?? "?",
                           short: p["short"] as? String ?? (p["name"] as? String ?? "?"),
                           folder: p["folder"] as? String ?? "",
                           out: p["out"] as? String ?? "")
            }
            IO.send(["ready": true])
        case "exit":
            WindowRunner.shared.suppressCloseMessage = true
            NSApp.terminate(nil)
        default:
            break
        }
    }
}

struct PickWindowView: View {
    @ObservedObject var model: PickVM

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(model.info)
                .foregroundColor(.secondary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
            Divider()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(model.presets.enumerated()), id: \.element.id) { index, preset in
                        if !preset.folder.isEmpty,
                           index == 0 || model.presets[index - 1].folder != preset.folder {
                            Text(preset.folder)
                                .font(.headline)
                                .padding(.top, 8)
                        }
                        HStack {
                            Text(preset.short)
                            Spacer()
                            Text(preset.out).foregroundColor(.secondary)
                            Button(str(model.strings, "convert", "Convert")) {
                                WindowRunner.shared.suppressCloseMessage = true
                                IO.send(["preset": preset.id])
                                NSApp.terminate(nil)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }
                .padding(12)
            }
        }
        .frame(minWidth: 380, minHeight: 300)
    }
}

// MARK: - Settings mode

struct SettingRowSpec: Identifiable {
    let id: String
    let key: String
    let label: String
    let kind: String       // "choice" | "int" | "float" | "bool"
    let options: [String]
    let minV: Double
    let maxV: Double
    let step: Double
    let defNum: Double
    let defBool: Bool

    init(_ d: [String: Any]) {
        key = d["key"] as? String ?? ""
        id = key
        label = d["label"] as? String ?? key
        kind = d["kind"] as? String ?? "int"
        options = (d["options"] as? [Any] ?? []).compactMap { $0 as? String }
        minV = (d["min"] as? NSNumber)?.doubleValue ?? 0
        maxV = (d["max"] as? NSNumber)?.doubleValue ?? 100
        step = (d["step"] as? NSNumber)?.doubleValue ?? 1
        defNum = (d["default"] as? NSNumber)?.doubleValue ?? 0
        defBool = (d["default"] as? NSNumber)?.boolValue ?? true
    }
}

final class PresetVM: ObservableObject, Identifiable {
    let id = UUID()
    @Published var name: String
    @Published var outputType: String
    @Published var inputTypes: Set<String>
    @Published var postAction: String
    @Published var template: String
    var settings: [String: Any]

    init(_ d: [String: Any]) {
        name = d["name"] as? String ?? "Preset"
        outputType = d["output_type"] as? String ?? "mp4"
        inputTypes = Set((d["input_types"] as? [Any] ?? []).compactMap { $0 as? String })
        postAction = d["input_post_action"] as? String ?? "none"
        template = d["output_template"] as? String ?? "(p)(f)"
        settings = d["settings"] as? [String: Any] ?? [:]
    }

    func toDict() -> [String: Any] {
        ["name": name,
         "output_type": outputType,
         "input_types": inputTypes.sorted(),
         "input_post_action": postAction,
         "output_template": template,
         "settings": settings]
    }

    func numBinding(_ row: SettingRowSpec, onChange: @escaping () -> Void) -> Binding<Double> {
        Binding(
            get: { (self.settings[row.key] as? NSNumber)?.doubleValue ?? row.defNum },
            set: { v in
                self.objectWillChange.send()
                self.settings[row.key] = row.kind == "int" ? Int(v.rounded()) as Any : (v * 100).rounded() / 100
                onChange()
            })
    }

    func boolBinding(_ row: SettingRowSpec, onChange: @escaping () -> Void) -> Binding<Bool> {
        Binding(
            get: { (self.settings[row.key] as? NSNumber)?.boolValue ?? row.defBool },
            set: { v in
                self.objectWillChange.send()
                self.settings[row.key] = v
                onChange()
            })
    }

    func choiceBinding(_ row: SettingRowSpec, onChange: @escaping () -> Void) -> Binding<String> {
        Binding(
            get: {
                var v = (self.settings[row.key] as? String ?? row.options.first ?? "").lowercased()
                if v == "h265" { v = "hevc" }
                return row.options.contains(v) ? v : (row.options.first ?? "")
            },
            set: { v in
                self.objectWillChange.send()
                self.settings[row.key] = v
                onChange()
            })
    }
}

final class SettingsVM: ObservableObject {
    @Published var presets: [PresetVM] = []
    @Published var selection: UUID?
    @Published var maxJobs = 2
    @Published var exitWhenDone = true
    @Published var hwLabel = ""
    @Published var langLabel = ""
    @Published var modified = false

    var exitDelay = 3
    var version = 2
    var outputTypes: [String] = []
    var extensions: [String] = []
    var postActions = ["none", "archive", "delete"]
    var hwLabels: [String] = []
    var hwModes: [String] = []
    var langLabels: [String] = []
    var langCodes: [String] = []
    var settingRows: [SettingRowSpec] = []
    var newPresetTemplate: [String: Any] = [:]
    @Published var strings: [String: String] = [:]

    var selected: PresetVM? { presets.first { $0.id == selection } }

    func handle(_ msg: [String: Any]) {
        switch msg["type"] as? String {
        case "init":
            let meta = msg["meta"] as? [String: Any] ?? [:]
            strings = meta["strings"] as? [String: String] ?? [:]
            outputTypes = (meta["output_types"] as? [Any] ?? []).compactMap { $0 as? String }
            extensions = (meta["extensions"] as? [Any] ?? []).compactMap { $0 as? String }
            postActions = (meta["post_actions"] as? [Any] ?? []).compactMap { $0 as? String }
            hwLabels = (meta["hw_labels"] as? [Any] ?? []).compactMap { $0 as? String }
            hwModes = (meta["hw_modes"] as? [Any] ?? []).compactMap { $0 as? String }
            langLabels = (meta["lang_labels"] as? [Any] ?? []).compactMap { $0 as? String }
            langCodes = (meta["lang_codes"] as? [Any] ?? []).compactMap { $0 as? String }
            settingRows = (meta["setting_rows"] as? [[String: Any]] ?? []).map { SettingRowSpec($0) }
            newPresetTemplate = meta["new_preset"] as? [String: Any] ?? [:]

            let s = msg["settings"] as? [String: Any] ?? [:]
            version = (s["version"] as? NSNumber)?.intValue ?? 2
            exitDelay = (s["exit_delay_seconds"] as? NSNumber)?.intValue ?? 3
            maxJobs = (s["max_simultaneous_conversions"] as? NSNumber)?.intValue ?? 2
            exitWhenDone = (s["exit_when_done"] as? NSNumber)?.boolValue ?? true
            let hwMode = s["hardware_acceleration"] as? String ?? "off"
            hwLabel = hwLabels.indices.contains(hwModes.firstIndex(of: hwMode) ?? -1)
                ? hwLabels[hwModes.firstIndex(of: hwMode)!] : (hwLabels.first ?? "")
            let lang = s["language"] as? String ?? "auto"
            langLabel = langLabels.indices.contains(langCodes.firstIndex(of: lang) ?? -1)
                ? langLabels[langCodes.firstIndex(of: lang)!] : (langLabels.first ?? "")
            presets = (s["presets"] as? [[String: Any]] ?? []).map { PresetVM($0) }
            selection = nil
            modified = false
            WindowRunner.shared.setTitle(str(strings, "title", "File Converter — Settings"))
            IO.send(["ready": true])
        case "saved":
            modified = false
            WindowRunner.shared.setTitle(str(strings, "title_saved", "File Converter — Settings (saved)"))
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
                guard let self, !self.modified else { return }
                WindowRunner.shared.setTitle(str(self.strings, "title", "File Converter — Settings"))
            }
        case "exit":
            WindowRunner.shared.suppressCloseMessage = true
            NSApp.terminate(nil)
        default:
            break
        }
    }

    func markModified() {
        if !modified {
            modified = true
            WindowRunner.shared.setTitle(str(strings, "title_modified", "File Converter — Settings *"))
        }
    }

    func toDict() -> [String: Any] {
        var hw = "off"
        if let i = hwLabels.firstIndex(of: hwLabel), hwModes.indices.contains(i) { hw = hwModes[i] }
        var lang = "auto"
        if let i = langLabels.firstIndex(of: langLabel), langCodes.indices.contains(i) { lang = langCodes[i] }
        return ["version": version,
                "max_simultaneous_conversions": maxJobs,
                "exit_when_done": exitWhenDone,
                "exit_delay_seconds": exitDelay,
                "hardware_acceleration": hw,
                "language": lang,
                "presets": presets.map { $0.toDict() }]
    }

    func save() { IO.send(["action": "save", "settings": toDict()]) }

    func addPreset() {
        let p = PresetVM(newPresetTemplate)
        presets.append(p)
        selection = p.id
        markModified()
    }

    func removeSelected() {
        guard let sel = selection, let idx = presets.firstIndex(where: { $0.id == sel }) else { return }
        presets.remove(at: idx)
        selection = nil
        markModified()
    }
}

struct PresetEditorView: View {
    @ObservedObject var model: SettingsVM
    @ObservedObject var preset: PresetVM

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(str(model.strings, "name", "Name:"))
                    TextField("", text: Binding(
                        get: { preset.name },
                        set: { preset.name = $0; model.markModified() }))
                        .textFieldStyle(.roundedBorder)
                }
                HStack {
                    Text(str(model.strings, "output", "Output:"))
                    Picker("", selection: Binding(
                        get: { preset.outputType },
                        set: { preset.outputType = $0; model.markModified() })) {
                        ForEach(model.outputTypes, id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 120)
                    Spacer()
                }

                Text(str(model.strings, "input_types", "Input types:")).font(.headline)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 70), alignment: .leading)],
                          alignment: .leading, spacing: 4) {
                    ForEach(model.extensions, id: \.self) { ext in
                        Toggle(ext, isOn: Binding(
                            get: { preset.inputTypes.contains(ext) },
                            set: { on in
                                if on { preset.inputTypes.insert(ext) }
                                else { preset.inputTypes.remove(ext) }
                                model.markModified()
                            }))
                            .toggleStyle(.checkbox)
                            .font(.caption)
                    }
                }

                Divider()
                Text(str(model.strings, "conversion_settings", "Conversion settings:")).font(.headline)
                ForEach(model.settingRows) { row in
                    HStack {
                        Text(row.label).frame(width: 200, alignment: .leading)
                        switch row.kind {
                        case "bool":
                            Toggle("", isOn: preset.boolBinding(row) { model.markModified() })
                                .labelsHidden()
                                .toggleStyle(.checkbox)
                        case "choice":
                            Picker("", selection: preset.choiceBinding(row) { model.markModified() }) {
                                ForEach(row.options, id: \.self) { Text($0).tag($0) }
                            }
                            .labelsHidden()
                            .frame(maxWidth: 140)
                        default:
                            let binding = preset.numBinding(row) { model.markModified() }
                            Stepper(value: binding, in: row.minV...row.maxV, step: row.step) {
                                Text(row.kind == "float"
                                     ? String(format: "%.2f", binding.wrappedValue)
                                     : String(Int(binding.wrappedValue)))
                                    .frame(minWidth: 52, alignment: .trailing)
                                    .font(.system(.body, design: .monospaced))
                            }
                        }
                        Spacer()
                    }
                }

                Divider()
                HStack {
                    Text(str(model.strings, "after_conversion", "After conversion:"))
                    Picker("", selection: Binding(
                        get: { preset.postAction },
                        set: { preset.postAction = $0; model.markModified() })) {
                        ForEach(model.postActions, id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 130)
                    Spacer()
                }
                HStack {
                    Text(str(model.strings, "output_template", "Output template:"))
                    TextField("", text: Binding(
                        get: { preset.template },
                        set: { preset.template = $0; model.markModified() }))
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.body, design: .monospaced))
                }
                Text(str(model.strings, "template_hint",
                         "Variables: (p) path, (f) filename, (o) output ext, (i) input ext"))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding(14)
        }
    }
}

struct SettingsWindowView: View {
    @ObservedObject var model: SettingsVM

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 8) {
                GroupBox(label: Text(str(model.strings, "global", "Global"))) {
                    VStack(alignment: .leading, spacing: 6) {
                        Stepper(value: Binding(
                            get: { model.maxJobs },
                            set: { model.maxJobs = $0; model.markModified() }), in: 1...16) {
                            Text("\(str(model.strings, "max_jobs", "Max jobs:")) \(model.maxJobs)")
                        }
                        Toggle(str(model.strings, "auto_close", "Auto-close when done"),
                               isOn: Binding(
                                get: { model.exitWhenDone },
                                set: { model.exitWhenDone = $0; model.markModified() }))
                            .toggleStyle(.checkbox)
                        HStack {
                            Text(str(model.strings, "gpu_accel", "GPU accel:"))
                            Picker("", selection: Binding(
                                get: { model.hwLabel },
                                set: { model.hwLabel = $0; model.markModified() })) {
                                ForEach(model.hwLabels, id: \.self) { Text($0).tag($0) }
                            }
                            .labelsHidden()
                        }
                        HStack {
                            Text(str(model.strings, "language", "Language:"))
                            Picker("", selection: Binding(
                                get: { model.langLabel },
                                set: { model.langLabel = $0; model.save() })) {
                                ForEach(model.langLabels, id: \.self) { Text($0).tag($0) }
                            }
                            .labelsHidden()
                        }
                    }
                    .padding(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                Text(str(model.strings, "presets", "Presets")).font(.headline)
                List(model.presets, selection: $model.selection) { preset in
                    PresetListRow(preset: preset)
                }
                HStack {
                    Button(str(model.strings, "add", "Add")) { model.addPreset() }
                    Button(str(model.strings, "remove", "Remove")) { model.removeSelected() }
                    Spacer()
                    Button(str(model.strings, "save", "Save")) { model.save() }
                        .keyboardShortcut("s", modifiers: .command)
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding(10)
            .frame(minWidth: 270, maxWidth: 360)

            Group {
                if let preset = model.selected {
                    PresetEditorView(model: model, preset: preset)
                } else {
                    Text(str(model.strings, "select_preset", "Select a preset to edit"))
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 720, minHeight: 480)
    }
}

struct PresetListRow: View {
    @ObservedObject var preset: PresetVM
    var body: some View {
        Text(preset.name).tag(preset.id)
    }
}

// MARK: - Entry point

@main
struct Main {
    static func main() {
        signal(SIGPIPE, SIG_IGN)
        let mode = CommandLine.arguments.dropFirst().first ?? "progress"

        switch mode {
        case "pick":
            let model = PickVM()
            IO.readLoop { model.handle($0) }
            WindowRunner.shared.run(title: "File Converter", width: 430, height: 540,
                                    minW: 380, minH: 300,
                                    view: PickWindowView(model: model))
        case "settings":
            let model = SettingsVM()
            IO.readLoop { model.handle($0) }
            WindowRunner.shared.run(title: "File Converter — Settings", width: 880, height: 640,
                                    minW: 720, minH: 480,
                                    view: SettingsWindowView(model: model))
        default:
            let model = ProgressVM()
            IO.readLoop { model.handle($0) }
            WindowRunner.shared.run(title: "File Converter", width: 560, height: 420,
                                    minW: 480, minH: 240,
                                    view: ProgressWindowView(model: model))
        }
    }
}
