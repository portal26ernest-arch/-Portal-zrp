import UIKit
import WebKit

/// Device-local Telegram + MAX container. No PORTAL JavaScript bridge is installed here,
/// so provider credentials/cookies cannot be forwarded to the company API by this view.
final class MessengerViewController: UIViewController, WKNavigationDelegate, WKUIDelegate {
    private static let telegramURL = URL(string: "https://web.telegram.org/a/")!
    private static let maxURL = URL(string: "https://web.max.ru/")!
    private let browser: WKWebView
    private let selector = UISegmentedControl(items: ["Telegram", "MAX"])
    private var provider: String

    init(provider: String) {
        self.provider = provider.lowercased() == "max" ? "max" : "telegram"
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        self.browser = WKWebView(frame: .zero, configuration: config)
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        selector.translatesAutoresizingMaskIntoConstraints = false
        browser.translatesAutoresizingMaskIntoConstraints = false
        selector.addTarget(self, action: #selector(providerChanged), for: .valueChanged)
        browser.navigationDelegate = self
        browser.uiDelegate = self

        let close = UIButton(type: .system)
        close.translatesAutoresizingMaskIntoConstraints = false
        close.setTitle("Закрыть", for: .normal)
        close.addTarget(self, action: #selector(closeMessenger), for: .touchUpInside)
        view.addSubview(selector); view.addSubview(close); view.addSubview(browser)
        let guide = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            selector.leadingAnchor.constraint(equalTo: guide.leadingAnchor, constant: 12),
            selector.topAnchor.constraint(equalTo: guide.topAnchor, constant: 8),
            close.leadingAnchor.constraint(equalTo: selector.trailingAnchor, constant: 8),
            close.trailingAnchor.constraint(equalTo: guide.trailingAnchor, constant: -12),
            close.centerYAnchor.constraint(equalTo: selector.centerYAnchor),
            close.widthAnchor.constraint(greaterThanOrEqualToConstant: 72),
            browser.topAnchor.constraint(equalTo: selector.bottomAnchor, constant: 8),
            browser.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            browser.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            browser.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
        selectProvider(provider)
    }

    static func isAllowedTopLevel(_ url: URL?) -> Bool {
        guard let url, url.scheme?.lowercased() == "https", url.user == nil, url.password == nil,
              url.port == nil || url.port == 443, let host = url.host?.lowercased() else { return false }
        return host == "web.telegram.org" || host == "web.max.ru"
    }

    func selectProvider(_ value: String) {
        provider = value.lowercased() == "max" ? "max" : "telegram"
        selector.selectedSegmentIndex = provider == "max" ? 1 : 0
        let target = provider == "max" ? Self.maxURL : Self.telegramURL
        if browser.url?.absoluteString.caseInsensitiveCompare(target.absoluteString) != .orderedSame {
            browser.load(URLRequest(url: target))
        }
    }

    @objc private func providerChanged() { selectProvider(selector.selectedSegmentIndex == 1 ? "max" : "telegram") }
    @objc private func closeMessenger() { dismiss(animated: true) }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard Self.isAllowedTopLevel(navigationAction.request.url) else { decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        return nil
    }
}
