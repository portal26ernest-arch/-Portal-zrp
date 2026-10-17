import SwiftUI

@main
struct PortalIOSApp: App {
    init() {
        RetiredProviderDataCleanup.performOnce()
    }

    var body: some Scene {
        WindowGroup {
            PortalWebView()
                .ignoresSafeArea()
        }
    }
}
