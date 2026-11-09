import AppKit
import Foundation

final class Session {
    let process = Process()
    let pipe = Pipe()
    let log: FileHandle
    let directory: URL
    let secrets: [String]
    var pending = Data()

    init(file: String?) throws {
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser
        let logs = home.appendingPathComponent("Library/Logs/RemoteViewer", isDirectory: true)
        try fm.createDirectory(at: logs, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        directory = fm.temporaryDirectory.appendingPathComponent("remote-viewer-" + UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let logURL = logs.appendingPathComponent(stamp + "-" + String(UUID().uuidString.prefix(8)) + ".log")
        fm.createFile(atPath: logURL.path, contents: nil, attributes: [.posixPermissions: 0o600])
        log = try FileHandle(forWritingTo: logURL)
        var args = ["--debug"]
        var sensitive: [String] = []
        if let file = file {
            let source = URL(fileURLWithPath: file)
            let content = try String(contentsOf: source, encoding: .utf8)
            for line in content.components(separatedBy: .newlines) {
                let pair = line.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
                if pair.count == 2, ["password", "host", "ca"].contains(pair[0].trimmingCharacters(in: .whitespaces).lowercased()) {
                    let value = pair[1].trimmingCharacters(in: .whitespaces)
                    if !value.isEmpty { sensitive.append(value) }
                }
            }
            let copy = directory.appendingPathComponent("connection.vv")
            try fm.copyItem(at: source, to: copy)
            try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: copy.path)
            args.append(copy.path)
        }
        secrets = sensitive.sorted { $0.count > $1.count }
        process.executableURL = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/Remote Viewer Native.app/Contents/MacOS/remote-viewer")
        process.arguments = args
        var env = ProcessInfo.processInfo.environment
        env.removeValue(forKey: "DISPLAY")
        env["GDK_BACKEND"] = "quartz"
        let native = Bundle.main.resourceURL!
        let helpers = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers")
        env["XDG_DATA_DIRS"] = native.appendingPathComponent("share").path
        env["GSETTINGS_SCHEMA_DIR"] = native.appendingPathComponent("share/glib-2.0/schemas").path
        env["GTK_DATA_PREFIX"] = native.path
        env["GTK_EXE_PREFIX"] = native.path
        env["FONTCONFIG_FILE"] = native.appendingPathComponent("fonts.conf").path
        env["GIO_MODULE_DIR"] = native.appendingPathComponent("gio/modules").path
        let plugins = native.appendingPathComponent("gstreamer-1.0").path
        env["GST_PLUGIN_PATH"] = plugins
        env["GST_PLUGIN_SYSTEM_PATH"] = plugins
        env["GST_PLUGIN_SCANNER"] = helpers.appendingPathComponent("gst-plugin-scanner").path
        let cache = home.appendingPathComponent("Library/Caches/RemoteViewer", isDirectory: true)
        try fm.createDirectory(at: cache, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        env["GST_REGISTRY"] = cache.appendingPathComponent("gstreamer-arm64.bin").path
        env["SSL_CERT_FILE"] = native.appendingPathComponent("cert.pem").path
        func moduleCache(_ program: String, _ modules: URL, _ name: String, _ variable: String, _ arguments: [String] = []) throws {
            let output = directory.appendingPathComponent(name)
            fm.createFile(atPath: output.path, contents: nil, attributes: [.posixPermissions: 0o600])
            let handle = try FileHandle(forWritingTo: output)
            let query = Process()
            query.executableURL = helpers.appendingPathComponent(program)
            var queryEnv = env
            queryEnv["GDK_PIXBUF_MODULEDIR"] = modules.path
            query.environment = queryEnv
            query.arguments = arguments
            query.standardOutput = handle
            query.standardError = log
            try query.run()
            query.waitUntilExit()
            try handle.close()
            guard query.terminationStatus == 0 else {
                throw NSError(domain: "RemoteViewer", code: 1, userInfo: [NSLocalizedDescriptionKey: "Не удалось создать кэш графических модулей. См. Library/Logs/RemoteViewer."])
            }
            env[variable] = output.path
        }
        let pixbuf = native.appendingPathComponent("pixbuf-loaders")
        try moduleCache("gdk-pixbuf-query-loaders", pixbuf, "pixbuf.cache", "GDK_PIXBUF_MODULE_FILE")
        let im = native.appendingPathComponent("immodules")
        let imFiles = try fm.contentsOfDirectory(at: im, includingPropertiesForKeys: nil).filter { $0.pathExtension == "so" }.map { $0.path }
        try moduleCache("gtk-query-immodules-3.0", im, "immodules.cache", "GTK_IM_MODULE_FILE", imFiles)
        env["GTK_IM_MODULE"] = "quartz"
        process.environment = env
        process.standardOutput = pipe
        process.standardError = pipe
        try log.write(contentsOf: Data("Remote Viewer launch: \(stamp)\nConnection file: \(file == nil ? "none" : "provided (private copy)")\n".utf8))
    }

    func scrub(_ text: String) -> String {
        var result = text
        for secret in secrets { result = result.replacingOccurrences(of: secret, with: "[redacted]") }
        result = result.replacingOccurrences(of: "pvespiceproxy:[^\\s'\"<>]+", with: "[redacted ticket]", options: .regularExpression)
        result = result.replacingOccurrences(of: "(?i)(password|ticket)([=: ]+)[^\\s]+", with: "$1$2[redacted]", options: .regularExpression)
        return result
    }

    func run(done: @escaping () -> Void) throws {
        try process.run()
        DispatchQueue.global(qos: .utility).async {
            // Keep incomplete lines together so secrets split across reads are also removed.
            while true {
                let chunk = self.pipe.fileHandleForReading.availableData
                if chunk.isEmpty { break }
                self.pending.append(chunk)
                while let newline = self.pending.firstIndex(of: 10) {
                    let line = self.pending.prefix(through: newline)
                    self.pending.removeSubrange(...newline)
                    try? self.log.write(contentsOf: Data(self.scrub(String(decoding: line, as: UTF8.self)).utf8))
                }
            }
            if !self.pending.isEmpty {
                try? self.log.write(contentsOf: Data(self.scrub(String(decoding: self.pending, as: UTF8.self)).utf8))
            }
            self.process.waitUntilExit()
            try? self.log.write(contentsOf: Data("\nExit code: \(self.process.terminationStatus)\n".utf8))
            try? self.log.close()
            try? FileManager.default.removeItem(at: self.directory)
            DispatchQueue.main.async { done() }
        }
    }
}

final class Delegate: NSObject, NSApplicationDelegate {
    var sessions: [UUID: Session] = [:]
    var receivedFiles = false

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        receivedFiles = true
        for filename in filenames { launch(filename) }
        sender.reply(toOpenOrPrint: .success)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            if !self.receivedFiles { self.launch(nil) }
        }
    }

    func launch(_ file: String?) {
        let id = UUID()
        do {
            let session = try Session(file: file)
            sessions[id] = session
            try session.run {
                self.sessions.removeValue(forKey: id)
                if self.sessions.isEmpty { NSApp.terminate(nil) }
            }
        } catch {
            sessions.removeValue(forKey: id)
            let alert = NSAlert()
            alert.messageText = "Не удалось запустить Remote Viewer"
            alert.informativeText = error.localizedDescription
            alert.runModal()
            if sessions.isEmpty { NSApp.terminate(nil) }
        }
    }
}

let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
