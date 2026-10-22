import AppKit
import Foundation
import Photos

struct Request: Decodable { let action: String; let uuids: [String]? }
func finish(_ result: [String: Any], _ code: Int32 = 0) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    if CommandLine.arguments.count == 3 {
        try! data.write(to: URL(fileURLWithPath: CommandLine.arguments[2]), options: .atomic)
    } else { FileHandle.standardOutput.write(data) }
    exit(code)
}
let input = CommandLine.arguments.count == 3 ? (try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) : FileHandle.standardInput.readDataToEndOfFile()
guard let request = try? JSONDecoder().decode(Request.self, from: input) else {
    finish(["ok": false, "error": "请求格式不正确"])
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
func statusName(_ status: PHAuthorizationStatus) -> String {
    switch status { case .authorized: return "authorized"; case .limited: return "limited"
    case .denied: return "denied"; case .restricted: return "restricted"
    default: return "notDetermined" }
}
func run() {
    let status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    if request.action == "status" || request.action == "authorize" {
        finish(["ok": true, "authorization": statusName(status)])
    }
    guard status == .authorized else {
        finish(["ok": false, "error": "请先授权完整照片访问，再重试。", "authorization": statusName(status)])
    }
    guard ["check", "trash"].contains(request.action), let ids = request.uuids, !ids.isEmpty,
          ids.count <= 120, Set(ids).count == ids.count,
          ids.allSatisfy({ UUID(uuidString: $0) != nil }) else {
        finish(["ok": false, "error": "无效的媒体清单"])
    }
    let wanted = Set(ids.map { $0.uppercased() })
    // Match library-provided identifiers; never guess a localIdentifier suffix.
    let options = PHFetchOptions()
    options.includeHiddenAssets = true
    options.predicate = NSPredicate(format: "mediaType == %d OR mediaType == %d",
                                   PHAssetMediaType.image.rawValue, PHAssetMediaType.video.rawValue)
    let fetched = PHAsset.fetchAssets(with: options)
    var assets: [PHAsset] = []
    fetched.enumerateObjects { asset, _, _ in
        let uuid = String(asset.localIdentifier.split(separator: "/")[0]).uppercased()
        if wanted.contains(uuid) { assets.append(asset) }
    }
    guard assets.count == ids.count else {
        finish(["ok": false, "error": "有项目已不存在或不在当前系统图库中；本次未删除任何项目。"])
    }
    guard assets.allSatisfy({ !$0.isFavorite && !$0.isHidden }) else {
        finish(["ok": false, "error": "清单含收藏或隐藏项目；本次已停止。"])
    }
    if request.action == "check" { finish(["ok": true, "count": assets.count]) }
    do {
        try PHPhotoLibrary.shared().performChangesAndWait {
            PHAssetChangeRequest.deleteAssets(assets as NSArray)
        }
        let remaining = PHAsset.fetchAssets(withLocalIdentifiers: assets.map { $0.localIdentifier }, options: nil)
        guard remaining.count == 0 else {
            finish(["ok": false, "uncertain": true, "error": "系统已接受操作，但尚未确认图库状态；请在照片应用中核对，勿重复提交。"])
        }
        finish(["ok": true, "deleted": ids])
    } catch {
        finish(["ok": false, "error": "系统未完成删除：\(error.localizedDescription)"])
    }
}
if request.action == "authorize" && PHPhotoLibrary.authorizationStatus(for: .readWrite) == .notDetermined {
    PHPhotoLibrary.requestAuthorization(for: .readWrite) { _ in DispatchQueue.main.async { run() } }
} else { DispatchQueue.main.async { run() } }
app.run()
