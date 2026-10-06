import UIKit
import WebKit
import Network

/// Device-local Telegram + MAX container. No PORTAL JavaScript bridge is installed here,
/// so provider credentials/cookies cannot be forwarded to the company API by this view.
final class MessengerViewController: UIViewController, WKNavigationDelegate, WKUIDelegate {
    private static let telegramURL = URL(string: "https://web.telegram.org/a/")!
    private static let maxURL = URL(string: "https://web.max.ru/")!
    private var browser: WKWebView
    private let selector = UISegmentedControl(items: ["Telegram", "MAX"])
    private var provider: String
    private var relayJSON: String
    private let status = UILabel()

    init(provider: String, relayJSON: String = "") {
        self.provider = provider.lowercased() == "max" ? "max" : "telegram"
        self.relayJSON = relayJSON
        self.browser = Self.makeBrowser(provider: self.provider, relayJSON: relayJSON)
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private static let telegramStoreId = UUID(uuidString: "68C88C71-9F9B-4D43-9D85-514C0B9065E2")!
    private static let maxStoreId = UUID(uuidString: "7F1B82E8-7E0A-4B93-B10D-271CD988C09A")!
    private static func providerStore(_ provider: String) -> (store: WKWebsiteDataStore, fixed: Bool) {
        if #available(iOS 17.0, *) {
            let identifier = provider == "max" ? maxStoreId : telegramStoreId
            if let store = try? WKWebsiteDataStore(forIdentifier: identifier) { return (store, true) }
            return (.nonPersistent(), false)
        }
        return (.default(), false)
    }

    private static func makeBrowser(provider: String, relayJSON: String) -> WKWebView {
        let config = WKWebViewConfiguration()
        let providerData = providerStore(provider)
        let store = providerData.store
        if #available(iOS 17.0, *) {
            if providerData.fixed, provider == "telegram", let ticket = ticket(relayJSON), ticket.enabled,
               let components = URLComponents(string: ticket.proxyURL), let host = components.host,
               let port = NWEndpoint.Port(rawValue: UInt16(components.port ?? 443)) {
                var proxy = ProxyConfiguration(httpCONNECTProxy: .hostPort(host: NWEndpoint.Host(host), port: port), tlsOptions: nil)
                proxy.applyCredential(username: ticket.username, password: ticket.password)
                proxy.allowFailover = false
                store.proxyConfigurations = [proxy]
            } else if providerData.fixed { store.proxyConfigurations = [] }
        }
        config.websiteDataStore = store
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.preferences.javaScriptCanOpenWindowsAutomatically = false
        let web = WKWebView(frame: .zero, configuration: config)
        return web
    }

    static func clear(completion: @escaping () -> Void) {
        if #available(iOS 17.0, *) {
            let group = DispatchGroup()
            for data in [providerStore("telegram"), providerStore("max")] { group.enter(); clearProviderData(in: data.store) { group.leave() } }
            group.notify(queue: .main, execute: completion)
        } else { clearProviderData(in: .default(), completion: completion) }
    }

    private static func clearProviderData(in store: WKWebsiteDataStore, completion: @escaping () -> Void) {
        store.fetchDataRecords(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes()) { records in
            let providers = records.filter { record in
                let domain = record.displayName.lowercased()
                return domain == "telegram.org" || domain == "web.telegram.org" || domain.hasSuffix(".telegram.org") ||
                    domain == "max.ru" || domain == "web.max.ru" || domain.hasSuffix(".max.ru")
            }
            guard !providers.isEmpty else { completion(); return }
            store.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), for: providers, completionHandler: completion)
        }
    }

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
        status.translatesAutoresizingMaskIntoConstraints = false
        status.textAlignment = .center
        status.font = .systemFont(ofSize: 12)
        view.addSubview(selector); view.addSubview(close); view.addSubview(status); view.addSubview(browser)
        let guide = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            selector.leadingAnchor.constraint(equalTo: guide.leadingAnchor, constant: 12),
            selector.topAnchor.constraint(equalTo: guide.topAnchor, constant: 8),
            close.leadingAnchor.constraint(equalTo: selector.trailingAnchor, constant: 8),
            close.trailingAnchor.constraint(equalTo: guide.trailingAnchor, constant: -12),
            close.centerYAnchor.constraint(equalTo: selector.centerYAnchor),
            close.widthAnchor.constraint(greaterThanOrEqualToConstant: 72),
            status.topAnchor.constraint(equalTo: selector.bottomAnchor, constant: 4),
            status.leadingAnchor.constraint(equalTo: guide.leadingAnchor, constant: 8),
            status.trailingAnchor.constraint(equalTo: guide.trailingAnchor, constant: -8),
            status.heightAnchor.constraint(equalToConstant: 22),
            browser.topAnchor.constraint(equalTo: status.bottomAnchor, constant: 4),
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

    private struct RelayTicket { let enabled: Bool; let required: Bool; let proxyURL: String; let username: String; let password: String }
    private static func ticket(_ raw: String) -> RelayTicket? {
        guard let data = raw.data(using: .utf8), let item = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              item["provider"] as? String == "telegram", let enabled = item["enabled"] as? Bool,
              let required = item["required"] as? Bool else { return nil }
        let proxyURL = item["proxy_url"] as? String ?? ""
        let username = item["username"] as? String ?? ""
        let password = item["password"] as? String ?? ""
        if enabled {
            guard let components = URLComponents(string: proxyURL), components.scheme == "https", components.host != nil,
                  components.user == nil, components.password == nil, components.path.isEmpty || components.path == "/",
                  components.query == nil, components.fragment == nil, username.count <= 256, !username.isEmpty,
                  password.count <= 256, !password.isEmpty,
                  let expires = item["expires_at"] as? String, let expiryDate = ISO8601DateFormatter().date(from: expires), expiryDate > Date() else { return nil }
        }
        return RelayTicket(enabled: enabled, required: required,
                           proxyURL: proxyURL, username: username, password: password)
    }

    func selectProvider(_ value: String, relayJSON: String? = nil) {
        let refreshTicket = relayJSON != nil
        if let relayJSON { self.relayJSON = relayJSON }
        let nextProvider = value.lowercased() == "max" ? "max" : "telegram"
        if nextProvider != provider || refreshTicket {
            browser.stopLoading(); browser.removeFromSuperview()
            provider = nextProvider
            browser = Self.makeBrowser(provider: provider, relayJSON: self.relayJSON)
            browser.navigationDelegate = self; browser.uiDelegate = self; browser.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(browser)
            NSLayoutConstraint.activate([browser.topAnchor.constraint(equalTo: status.bottomAnchor, constant: 4), browser.leadingAnchor.constraint(equalTo: view.leadingAnchor), browser.trailingAnchor.constraint(equalTo: view.trailingAnchor), browser.bottomAnchor.constraint(equalTo: view.bottomAnchor)])
        } else { provider = nextProvider }
        selector.selectedSegmentIndex = provider == "max" ? 1 : 0
        let ticket = Self.ticket(self.relayJSON)
        if provider == "telegram", ticket == nil || ((ticket?.required == true) && ticket?.enabled != true) ||
            ((ticket?.enabled == true) && (ticket?.username.isEmpty != false || ticket?.password.isEmpty != false)) {
            status.text = "Telegram доступен только через защищённый канал PORTAL; канал пока недоступен."
            browser.loadHTMLString("", baseURL: nil)
            return
        }
        if #unavailable(iOS 17.0) {
            if provider == "telegram", ticket?.enabled == true {
                status.text = "Защищённый канал Telegram требует iOS 17 или новее."
                browser.loadHTMLString("", baseURL: nil)
                return
            }
        }
        status.text = provider == "telegram" && ticket?.enabled == true ? "Telegram: защищённый канал PORTAL" : "MAX: прямое подключение"
        let target = provider == "max" ? Self.maxURL : Self.telegramURL
        if browser.url?.absoluteString.caseInsensitiveCompare(target.absoluteString) != .orderedSame {
            browser.load(URLRequest(url: target))
        }
    }

    @objc private func providerChanged() { selectProvider(selector.selectedSegmentIndex == 1 ? "max" : "telegram") }
    @objc private func closeMessenger() { dismiss(animated: true) }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.targetFrame?.isMainFrame == false {
            decisionHandler(.allow)
            return
        }
        guard navigationAction.targetFrame?.isMainFrame == true else { decisionHandler(.cancel); return }
        guard Self.isAllowedTopLevel(navigationAction.request.url) else { decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        return nil
    }
}
