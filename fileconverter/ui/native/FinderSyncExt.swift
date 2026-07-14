// FinderSyncExt — Finder Sync extension: puts a real "File Converter"
// submenu in Finder's right-click menu, exactly like the Dolphin/Nemo
// submenus on Linux.
//
// The preset list (and its translations) comes from menu.json, written by
// the Python side on every install/settings save, so the menu never drifts
// from the config. Filtering happens HERE, per extension — no UTI matching
// involved, so .mkv & friends always get the right entries.
//
// Menu clicks never spawn work directly: they open a fileconverter:// URL,
// handled by the (unsandboxed) host app, which runs the usual launcher —
// same code path as the terminal and the Quick Actions.

import AppKit
import FinderSync
import Foundation

struct MenuPreset {
    let name: String
    let short: String
    let extensions: Set<String>
}

final class FinderSync: FIFinderSync {

    override init() {
        super.init()
        // Whole filesystem: the converter is meaningful anywhere.
        FIFinderSyncController.default().directoryURLs = [URL(fileURLWithPath: "/")]
    }

    // MARK: menu.json

    private var menuConfigURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".local/share/fileconverter/menu.json")
    }

    private func loadConfig() -> (presets: [MenuPreset], strings: [String: String]) {
        guard let data = try? Data(contentsOf: menuConfigURL),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else { return ([], [:]) }
        let strings = obj["strings"] as? [String: String] ?? [:]
        let presets = (obj["presets"] as? [[String: Any]] ?? []).compactMap { p -> MenuPreset? in
            guard let name = p["name"] as? String else { return nil }
            let exts = (p["extensions"] as? [Any] ?? []).compactMap { ($0 as? String)?.lowercased() }
            return MenuPreset(name: name,
                              short: p["short"] as? String ?? name,
                              extensions: Set(exts))
        }
        return (presets, strings)
    }

    // MARK: Context menu

    override func menu(for menuKind: FIMenuKind) -> NSMenu? {
        guard menuKind == .contextualMenuForItems else { return nil }
        let selected = FIFinderSyncController.default().selectedItemURLs() ?? []
        guard !selected.isEmpty else { return nil }

        // Only offer presets that accept EVERY selected file (Linux rule).
        var exts = Set<String>()
        for url in selected {
            let e = url.pathExtension.lowercased()
            if e.isEmpty { return nil }   // folders / extension-less files
            exts.insert(e)
        }

        let (presets, strings) = loadConfig()
        let compatible = presets.filter { exts.isSubset(of: $0.extensions) }
        guard !compatible.isEmpty else { return nil }

        let submenu = NSMenu(title: "")
        for preset in compatible {
            let item = NSMenuItem(title: preset.short,
                                  action: #selector(convertAction(_:)),
                                  keyEquivalent: "")
            item.target = self
            item.representedObject = preset.name
            submenu.addItem(item)
        }
        submenu.addItem(.separator())
        let configure = NSMenuItem(title: strings["configure"] ?? "Configure presets...",
                                   action: #selector(configureAction(_:)),
                                   keyEquivalent: "")
        configure.target = self
        submenu.addItem(configure)

        let root = NSMenuItem(title: strings["menu_title"] ?? "File Converter",
                              action: nil, keyEquivalent: "")
        root.submenu = submenu
        let menu = NSMenu(title: "")
        menu.addItem(root)
        return menu
    }

    // MARK: Actions → fileconverter:// URL → host app

    @objc private func convertAction(_ sender: NSMenuItem) {
        guard let preset = sender.representedObject as? String else { return }
        let files = FIFinderSyncController.default().selectedItemURLs() ?? []
        guard !files.isEmpty else { return }
        var comps = URLComponents()
        comps.scheme = "fileconverter"
        comps.host = "convert"
        var items = [URLQueryItem(name: "preset", value: preset)]
        items += files.map { URLQueryItem(name: "f", value: $0.path) }
        comps.queryItems = items
        if let url = comps.url {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func configureAction(_ sender: NSMenuItem) {
        if let url = URL(string: "fileconverter://settings") {
            NSWorkspace.shared.open(url)
        }
    }
}
