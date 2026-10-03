import SwiftUI

@main
struct PortalIOSApp: App {
    var body: some Scene {
        WindowGroup {
            PortalWebView()
                .ignoresSafeArea()
        }
    }
}
