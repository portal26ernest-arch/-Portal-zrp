import SwiftUI
import WebKit

struct PortalWebView: UIViewRepresentable {
    final class Coordinator {
        var bridge: PortalNativeBridge?
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let bridge = PortalNativeBridge()
        bridge.install(into: configuration.userContentController)
        context.coordinator.bridge = bridge

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.isOpaque = false
        webView.backgroundColor = .systemBackground
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.navigationDelegate = bridge
        bridge.webView = webView
        let bundle = Bundle.main
        let index = bundle.url(forResource: "index", withExtension: "html", subdirectory: "assets")
            ?? bundle.url(forResource: "index", withExtension: "html")

        if let index {
            let access = index.deletingLastPathComponent()
            webView.loadFileURL(index, allowingReadAccessTo: access)
        } else {
            webView.loadHTMLString(
                "<html><body><h2>PORTAL</h2><p>Не найден общий мобильный интерфейс.</p></body></html>",
                baseURL: nil
            )
        }

        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        coordinator.bridge?.detach()
        webView.stopLoading()
        webView.navigationDelegate = nil
        coordinator.bridge = nil
    }
}
