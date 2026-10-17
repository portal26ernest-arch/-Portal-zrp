import Foundation
import WebKit

/// One-time retirement of external provider web sessions from older PORTAL builds.
/// Never wipes the shared PORTAL WKWebsiteDataStore or its outbox/cache.
enum RetiredProviderDataCleanup {
    private static let doneKey = "portal_retired_external_provider_stores_v1"
    private static let legacyProviderStores: [UUID] = [
        UUID(uuidString: "68C88C71-9F9B-4D43-9D85-514C0B9065E2")!,
        UUID(uuidString: "7F1B82E8-7E0A-4B93-B10D-271CD988C09A")!
    ]

    static func performOnce() {
        guard !UserDefaults.standard.bool(forKey: doneKey) else { return }
        DispatchQueue.main.async {
            let types = WKWebsiteDataStore.allWebsiteDataTypes()
            let group = DispatchGroup()
            var succeeded = true
            if #available(iOS 17.0, *) {
                for identifier in legacyProviderStores {
                    guard let store = try? WKWebsiteDataStore(forIdentifier: identifier) else {
                        succeeded = false
                        continue
                    }
                    group.enter()
                    // This identifier was used solely for one retired provider.
                    store.removeData(ofTypes: types, modifiedSince: .distantPast) {
                        group.leave()
                    }
                }
            } else {
                // Older iOS used the default store. Remove only provider domains.
                let store = WKWebsiteDataStore.default()
                group.enter()
                store.fetchDataRecords(ofTypes: types) { records in
                    let retired = records.filter { record in
                        let host = record.displayName.lowercased()
                        return host == "telegram.org" || host.hasSuffix(".telegram.org")
                            || host == "max.ru" || host.hasSuffix(".max.ru")
                    }
                    guard !retired.isEmpty else { group.leave(); return }
                    store.removeData(ofTypes: types, for: retired) {
                        group.leave()
                    }
                }
            }
            group.notify(queue: .main) {
                if succeeded { UserDefaults.standard.set(true, forKey: doneKey) }
            }
        }
    }
}
