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
    /// Folder the entry belongs in, "" for top level. Presets ship in families
    /// ("Scale 720p", "Rotate left", ...) whose members share a short name, so
    /// a flat menu would list "To Mp4" seven times over.
    let folder: String
    let extensions: Set<String>
}

final class FinderSync: FIFinderSync {

    /// What the last menu was built from.
    ///
    /// The menu crosses into Finder's process and what comes back on a click
    /// is a rebuilt NSMenuItem: `representedObject` arrives empty, so the
    /// preset name has to travel as the item's integer `tag`. The selection
    /// makes the same trip — asking FIFinderSyncController for it again at
    /// click time can answer with nothing. Both used to be read straight from
    /// the sender, both failed a guard, and the guard returned in silence: the
    /// submenu looked alive and simply converted nothing, ever.
    ///
    /// Tags are 1-based on purpose. A tag that did not survive reads as 0, and
    /// 0 must not quietly select the first preset — converting with the wrong
    /// preset is worse than not converting at all.
    private var menuPresets: [String] = []
    private var menuSelection: [URL] = []

    override init() {
        super.init()
        // Whole filesystem: the converter is meaningful anywhere.
        FIFinderSyncController.default().directoryURLs = [URL(fileURLWithPath: "/")]
    }

    // MARK: menu.json

    private var menuConfigURL: URL {
        // App extensions run sandboxed, where homeDirectoryForCurrentUser
        // (and NSHomeDirectory) return the extension's *container*, not the
        // user's home — menu.json would never be found and the submenu would
        // silently never appear. getpwuid gives the real home; the bundle's
        // home-relative read-only entitlement is what grants access to it.
        let home = String(cString: getpwuid(getuid())!.pointee.pw_dir)
        return URL(fileURLWithPath: home)
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
                              folder: p["folder"] as? String ?? "",
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

        menuSelection = selected
        menuPresets = compatible.map { $0.name }

        let submenu = NSMenu(title: "")

        func makeItem(_ preset: MenuPreset, tag: Int) -> NSMenuItem {
            let item = NSMenuItem(title: preset.short,
                                  action: #selector(convertAction(_:)),
                                  keyEquivalent: "")
            item.target = self
            item.tag = tag + 1
            item.representedObject = preset.name
            return item
        }

        // Top-level entries keep their position in the list; each family folds
        // into one submenu, placed where its first member appeared. Nautilus
        // groups the same way, so both platforms read alike.
        var folderMenus: [String: NSMenu] = [:]
        for (index, preset) in compatible.enumerated() {
            if preset.folder.isEmpty {
                submenu.addItem(makeItem(preset, tag: index))
                continue
            }
            if folderMenus[preset.folder] == nil {
                let child = NSMenu(title: preset.folder)
                folderMenus[preset.folder] = child
                let holder = NSMenuItem(title: preset.folder, action: nil, keyEquivalent: "")
                holder.submenu = child
                submenu.addItem(holder)
            }
            folderMenus[preset.folder]?.addItem(makeItem(preset, tag: index))
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
        let tagged = sender.tag - 1
        let preset = (sender.representedObject as? String)
            ?? (menuPresets.indices.contains(tagged) ? menuPresets[tagged] : nil)
        guard let preset, !preset.isEmpty else {
            NSLog("FileConverterSync: menu click carried no preset (tag %ld)",
                  sender.tag)
            return
        }
        var files = menuSelection
        if files.isEmpty {
            files = FIFinderSyncController.default().selectedItemURLs() ?? []
        }
        guard !files.isEmpty else {
            NSLog("FileConverterSync: menu click carried no selection")
            return
        }
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
