import CryptoKit
import Foundation
import Security

final class PortalLocalCache {
    private let maxPayload = 8 * 1024 * 1024
    private let maxOutboxItem = 512 * 1024
    private let maxOutboxItems = 1000
    private let maxAge: TimeInterval = 30 * 24 * 60 * 60
    private let fileManager = FileManager.default
    private let keyService = "ru.portal.app.ios.local-cache"
    private let keyAccount = "portal-local-cache-v1"

    private struct Envelope: Codable {
        let v: Int
        let savedAt: TimeInterval
        let data: Data
    }

    private var portalRoot: URL? {
        try? fileManager.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("PORTAL", isDirectory: true)
    }

    private var root: URL? { portalRoot?.appendingPathComponent("company-cache", isDirectory: true) }
    private var outboxRoot: URL? { portalRoot?.appendingPathComponent("company-outbox", isDirectory: true) }

    func read(serverOrigin: String, companyID: String, cacheKey: String) -> [String: Any]? {
        guard let target = cacheFile(serverOrigin: serverOrigin, companyID: companyID, cacheKey: cacheKey),
              let sealed = try? Data(contentsOf: target),
              sealed.count <= maxPayload * 2,
              let plain = try? AES.GCM.open(AES.GCM.SealedBox(combined: sealed), using: symmetricKey()),
              plain.count <= maxPayload,
              let envelope = try? JSONDecoder().decode(Envelope.self, from: plain),
              envelope.v == 1,
              Date().timeIntervalSince1970 - envelope.savedAt <= maxAge,
              let object = try? JSONSerialization.jsonObject(with: envelope.data) as? [String: Any],
              object["ok"] as? Bool == true else { return nil }
        return object
    }

    @discardableResult
    func write(serverOrigin: String, companyID: String, cacheKey: String, object: [String: Any]) -> Bool {
        guard object["ok"] as? Bool == true,
              JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object),
              data.count > 0, data.count <= maxPayload,
              let target = cacheFile(serverOrigin: serverOrigin, companyID: companyID, cacheKey: cacheKey) else { return false }
        do {
            let envelope = Envelope(v: 1, savedAt: Date().timeIntervalSince1970, data: data)
            let plain = try JSONEncoder().encode(envelope)
            let sealed = try AES.GCM.seal(plain, using: symmetricKey())
            guard let combined = sealed.combined else { return false }
            try fileManager.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
            try combined.write(to: target, options: [.atomic, .completeFileProtectionUnlessOpen])
            return true
        } catch {
            return false
        }
    }

    @discardableResult
    func clearCompany(serverOrigin: String, companyID: String) -> Bool {
        guard let directory = companyDirectory(serverOrigin: serverOrigin, companyID: companyID) else { return false }
        guard fileManager.fileExists(atPath: directory.path) else { return true }
        do {
            try fileManager.removeItem(at: directory)
            return true
        } catch {
            return false
        }
    }

    @discardableResult
    func delete(serverOrigin: String, companyID: String, cacheKey: String) -> Bool {
        guard let target = cacheFile(serverOrigin: serverOrigin, companyID: companyID, cacheKey: cacheKey) else { return false }
        guard fileManager.fileExists(atPath: target.path) else { return true }
        do {
            try fileManager.removeItem(at: target)
            return true
        } catch {
            return false
        }
    }


    @discardableResult
    func enqueueMutation(serverOrigin: String, companyID: String, requestID: String, json: String) -> Bool {
        guard requestID.range(of: #"^[0-9A-Fa-f-]{36}$"#, options: .regularExpression) != nil,
              let data = json.data(using: .utf8), !data.isEmpty, data.count <= maxOutboxItem,
              let directory = outboxDirectory(serverOrigin: serverOrigin, companyID: companyID) else { return false }
        do {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
            let existing = try fileManager.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
                .filter { $0.pathExtension == "bin" }
            guard existing.count < maxOutboxItems else { return false }
            let sealed = try AES.GCM.seal(data, using: symmetricKey())
            guard let combined = sealed.combined else { return false }
            let target = directory.appendingPathComponent(hash(requestID) + ".bin", isDirectory: false)
            try combined.write(to: target, options: [.atomic, .completeFileProtectionUnlessOpen])
            return true
        } catch {
            return false
        }
    }

    func pendingMutations(serverOrigin: String, companyID: String) -> [String] {
        guard let directory = outboxDirectory(serverOrigin: serverOrigin, companyID: companyID),
              let urls = try? fileManager.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: [.contentModificationDateKey],
                options: [.skipsHiddenFiles]
              ) else { return [] }
        let sorted = urls.filter { $0.pathExtension == "bin" }.sorted {
            ((try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) <
            ((try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast)
        }
        return sorted.compactMap { url in
            guard let combined = try? Data(contentsOf: url),
                  combined.count <= maxOutboxItem * 2,
                  let plain = try? AES.GCM.open(AES.GCM.SealedBox(combined: combined), using: symmetricKey()),
                  plain.count <= maxOutboxItem else { return nil }
            return String(data: plain, encoding: .utf8)
        }
    }

    @discardableResult
    func removeMutation(serverOrigin: String, companyID: String, requestID: String) -> Bool {
        guard requestID.range(of: #"^[0-9A-Fa-f-]{36}$"#, options: .regularExpression) != nil,
              let directory = outboxDirectory(serverOrigin: serverOrigin, companyID: companyID) else { return false }
        let target = directory.appendingPathComponent(hash(requestID) + ".bin", isDirectory: false)
        guard fileManager.fileExists(atPath: target.path) else { return true }
        do {
            try fileManager.removeItem(at: target)
            return true
        } catch {
            return false
        }
    }

    func pendingMutationCount(serverOrigin: String, companyID: String) -> Int {
        guard let directory = outboxDirectory(serverOrigin: serverOrigin, companyID: companyID),
              let urls = try? fileManager.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        else { return 0 }
        return urls.filter { $0.pathExtension == "bin" }.count
    }

    private func outboxDirectory(serverOrigin: String, companyID: String) -> URL? {
        guard !serverOrigin.isEmpty,
              companyID.range(of: #"^[1-9][0-9]{0,9}$"#, options: .regularExpression) != nil,
              let outboxRoot else { return nil }
        return outboxRoot.appendingPathComponent(hash(serverOrigin.lowercased()), isDirectory: true)
            .appendingPathComponent(companyID, isDirectory: true)
    }

    private func cacheFile(serverOrigin: String, companyID: String, cacheKey: String) -> URL? {
        guard !cacheKey.isEmpty, cacheKey.utf8.count <= 2048,
              let directory = companyDirectory(serverOrigin: serverOrigin, companyID: companyID) else { return nil }
        return directory.appendingPathComponent(hash(cacheKey) + ".bin", isDirectory: false)
    }

    private func companyDirectory(serverOrigin: String, companyID: String) -> URL? {
        guard !serverOrigin.isEmpty,
              companyID.range(of: #"^[1-9][0-9]{0,9}$"#, options: .regularExpression) != nil,
              let root else { return nil }
        return root.appendingPathComponent(hash(serverOrigin.lowercased()), isDirectory: true)
            .appendingPathComponent(companyID, isDirectory: true)
    }

    private func hash(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private func symmetricKey() throws -> SymmetricKey {
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keyService,
            kSecAttrAccount as String: keyAccount
        ]
        var lookup = base
        lookup[kSecReturnData as String] = true
        lookup[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(lookup as CFDictionary, &item)
        if status == errSecSuccess, let data = item as? Data, data.count == 32 {
            return SymmetricKey(data: data)
        }
        guard status == errSecItemNotFound else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(status)) }
        var bytes = Data(count: 32)
        let randomStatus = bytes.withUnsafeMutableBytes { ptr in
            SecRandomCopyBytes(kSecRandomDefault, 32, ptr.baseAddress!)
        }
        guard randomStatus == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(randomStatus)) }
        var insert = base
        insert[kSecValueData as String] = bytes
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(insert as CFDictionary, nil)
        if addStatus == errSecDuplicateItem { return try symmetricKey() }
        guard addStatus == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(addStatus)) }
        return SymmetricKey(data: bytes)
    }
}
