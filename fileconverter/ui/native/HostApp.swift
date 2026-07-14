// FileConverterHost — the tiny background app inside "File Converter.app".
//
// Two jobs:
//   1. Handle fileconverter:// URLs sent by the Finder Sync extension
//      (fileconverter://convert?preset=To%20Mp4&f=/path/a.mkv&f=/path/b.mkv
//       and fileconverter://settings) by running the regular launcher.
//   2. On a plain double-click launch (no URL), open the settings window —
//      this app doubles as the Dock-visible settings entry.
//
// It is deliberately NOT sandboxed: the sandboxed Finder extension delegates
// here so conversions run with normal file access.
//
// The app stays alive until every spawned conversion exits. That is not
// cosmetic: as long as this app is the running "responsible process", TCC
// folder prompts (Downloads, Desktop, Documents...) are asked — and stored —
// in the name of "File Converter", not of the venv's "python3.x" binary.

import AppKit
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var handledURL = false
    private var activeChildren = 0

    private var launcher: String {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".local/bin/fileconverter").path
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        handledURL = true
        for url in urls {
            handle(url)
        }
        scheduleQuitIfIdle()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // URL opens arrive right after launch; give them a moment before
        // deciding this was a plain double-click.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
            guard let self, !self.handledURL else { return }
            self.spawn([self.launcher, "--settings"])
            self.scheduleQuitIfIdle()
        }
    }

    private func handle(_ url: URL) {
        guard url.scheme == "fileconverter" else { return }
        switch url.host {
        case "convert":
            let comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
            let items = comps?.queryItems ?? []
            guard let preset = items.first(where: { $0.name == "preset" })?.value,
                  !preset.isEmpty else { return }
            let files = items.filter { $0.name == "f" }.compactMap { $0.value }
            guard !files.isEmpty else { return }
            spawn([launcher, "--conversion-preset", preset] + files)
        case "settings":
            spawn([launcher, "--settings"])
        default:
            break
        }
    }

    private func spawn(_ argv: [String]) {
        guard let exe = argv.first, FileManager.default.isExecutableFile(atPath: exe) else { return }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: exe)
        proc.arguments = Array(argv.dropFirst())
        do {
            try proc.run()
        } catch {
            NSLog("FileConverterHost: failed to run \(exe): \(error)")
            return
        }
        // Stay alive (and TCC-responsible) until this child finishes.
        activeChildren += 1
        DispatchQueue.global().async {
            proc.waitUntilExit()
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.activeChildren -= 1
                self.scheduleQuitIfIdle()
            }
        }
    }

    private func scheduleQuitIfIdle() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            if self.activeChildren == 0 {
                NSApp.terminate(nil)
            }
        }
    }
}

@main
struct HostMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
}
