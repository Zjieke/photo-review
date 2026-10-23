import AppKit
import Foundation

// This app is only a launch carrier: every product interaction lives in the browser.
final class BrowserLauncher: NSObject, NSApplicationDelegate {
    private var backend: Process?
    private var log: FileHandle?

    func applicationDidFinishLaunching(_ notification: Notification) {
        launch(primary: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        launch(primary: false)
        return false
    }

    private func launch(primary: Bool) {
        do {
            guard let resources = Bundle.main.resourceURL else {
                throw NSError(domain: "PhotoReview", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "应用资源缺失，请重新下载完整安装包。"])
            }
            let data = ProcessInfo.processInfo.environment["PHOTO_REVIEW_DATA_DIR"].map {
                URL(fileURLWithPath: $0, isDirectory: true)
            } ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("Photo Review", isDirectory: true)
            try FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
            let logs = data.appendingPathComponent("logs", isDirectory: true)
            try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
            let logURL = logs.appendingPathComponent("launcher.log")
            if !FileManager.default.fileExists(atPath: logURL.path) {
                FileManager.default.createFile(atPath: logURL.path, contents: nil)
            }
            let stream = try FileHandle(forWritingTo: logURL)
            stream.seekToEndOfFile()
            log = stream
            let process = Process()
            process.executableURL = resources.appendingPathComponent("runtime/bin/python3")
            process.arguments = [resources.appendingPathComponent("project/launcher.py").path, "--packaged"]
            process.currentDirectoryURL = data
            var environment = ProcessInfo.processInfo.environment
            environment.removeValue(forKey: "PYTHONHOME")
            environment.removeValue(forKey: "PYTHONPATH")
            environment["PYTHONNOUSERSITE"] = "1"
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            environment["PHOTO_REVIEW_DATA_DIR"] = data.path
            environment["PHOTO_REVIEW_PACKAGED"] = "1"
            environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
            process.environment = environment
            process.standardOutput = stream
            process.standardError = stream
            if primary {
                backend = process
                process.terminationHandler = { finished in
                    DispatchQueue.main.async {
                        if finished.terminationStatus != 0 {
                            self.showError("启动未完成。可查看日志：\n\(logURL.path)\n\n请将错误说明反馈给项目维护者。")
                        }
                        NSApplication.shared.terminate(nil)
                    }
                }
            }
            try process.run()
        } catch {
            showError(error.localizedDescription)
            if primary { NSApplication.shared.terminate(nil) }
        }
    }

    private func showError(_ text: String) {
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "照片整理器启动失败"
        alert.informativeText = text
        alert.alertStyle = .warning
        alert.addButton(withTitle: "知道了")
        alert.runModal()
    }
}

let delegate = BrowserLauncher()
let application = NSApplication.shared
application.setActivationPolicy(.accessory)
application.delegate = delegate
application.run()
