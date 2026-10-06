import Foundation
import UIKit
import WebKit
import UserNotifications

final class PortalNativeBridge: NSObject, WKScriptMessageHandler, WKScriptMessageHandlerWithReply, WKNavigationDelegate {
    static let handlerName = "portalNative"
    static let replyHandlerName = "portalNativeReply"
    static let allowedExternalHosts: Set<String> = ["seller.ozon.ru", "seller.wildberries.ru"]
    static let localOutboxPaths: Set<String> = ["/api/v3/work", "/api/v3/links", "/api/v3/batches", "/api/v3/tasks", "/api/v3/shipments", "/api/v3/returns"]
    static let serverDiscoveryURL = URL(string: "https://raw.githubusercontent.com/portal26ernest-arch/-Portal-zrp/main/portal-server.json")!
    weak var webView: WKWebView?

    private let defaults = UserDefaults.standard
    private let localCache = PortalLocalCache()
    private var cacheCompany = ""
    private var messengerClearInProgress = false
    private var pendingMessengerProvider: String?
    private var userContentController: WKUserContentController?
    private var activeObserver: NSObjectProtocol?

    private var defaultServer: String {
        (Bundle.main.object(forInfoDictionaryKey: "PORTALDefaultAPIURL") as? String) ?? "https://portal.invalid"
    }

    private var serverURL: String {
        let saved = defaults.string(forKey: "portal_server_url") ?? ""
        return Self.isValidServerURL(saved) ? saved : defaultServer
    }

    static func isValidServerURL(_ value: String) -> Bool {
        guard let components = URLComponents(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(components.scheme?.lowercased() ?? ""),
              let host = components.host?.lowercased(), !host.isEmpty,
              components.scheme?.lowercased() == "https" || isLoopbackHost(host),
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil else { return false }
        return components.path.isEmpty || components.path == "/"
    }

    private static func isLoopbackHost(_ host: String) -> Bool {
        host == "localhost" || host.hasSuffix(".localhost") || host == "::1" || host == "[::1]" ||
            host.range(of: #"^127(?:\.\d{1,3}){3}$"#, options: .regularExpression) != nil
    }
    static func isAllowedExternalURL(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "https",
              let host = url.host?.lowercased(),
              allowedExternalHosts.contains(host),
              url.user == nil, url.password == nil,
              url.port == nil || url.port == 443 else { return false }
        return true
    }

    static func normalizeOfficialServerURL(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard var components = URLComponents(string: trimmed),
              components.scheme?.lowercased() == "https",
              let host = components.host?.lowercased(), !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil,
              components.port == nil || components.port == 443,
              components.path.isEmpty || components.path == "/",
              host == "api.vart-portal.ru" || host == "reserve-api.vart-portal.ru" else { return nil }
        components.scheme = "https"
        components.host = host
        components.port = nil
        components.path = ""
        return components.string?.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    private static func jsonString(_ value: String) -> String {
        let data = try! JSONEncoder().encode(value)
        return String(data: data, encoding: .utf8)!
    }

    private static func jsonObjectString(_ object: [String: Any]) -> String {
        guard JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object),
              let value = String(data: data, encoding: .utf8) else { return "{}" }
        return value
    }

    private var metadata: [String: Any] {
        let info = Bundle.main.infoDictionary ?? [:]
        let version = info["CFBundleShortVersionString"] as? String ?? "0"
        let build = info["CFBundleVersion"] as? String ?? "0"
        return [
            "applicationId": Bundle.main.bundleIdentifier ?? "ru.portal.app.ios",
            "versionName": version,
            "versionCode": Int(build) ?? 0,
            "buildNumber": info["PORTALBuildNumber"] as? String ?? version,
            "buildDate": info["PORTALBuildDate"] as? String ?? "",
            "channel": info["PORTALReleaseChannel"] as? String ?? "development",
            "updatesConfigured": true,
            "platform": "iOS"
        ]
    }
    private func bootstrapScript() -> String {
        let metadataJSON = Self.jsonObjectString(metadata)
        let metadataLiteral = Self.jsonString(metadataJSON)
        let serverLiteral = Self.jsonString(serverURL)
        let buildLiteral = Self.jsonString("PORTAL iOS · Build \(metadata["versionName"] ?? "0")")

        return """
        (function(){
          const native = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.\(Self.handlerName);
          const nativeReply = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.\(Self.replyHandlerName);
          if (!native) return;
          let server = \(serverLiteral);
          let cacheCompany = '';
          const metadata = \(metadataLiteral);
          const send = (action, payload) => native.postMessage(Object.assign({action:action}, payload || {}));
          const ask = (action, payload) => nativeReply ? nativeReply.postMessage(Object.assign({action:action}, payload || {})) : Promise.resolve(null);
          const validServer = value => {
            try {
              const u = new URL(String(value || '').trim());
              return (u.protocol === 'http:' || u.protocol === 'https:') &&
                !u.username && !u.password && !u.search && !u.hash && (u.pathname === '/' || u.pathname === '');
            } catch { return false; }
          };
          window.__portalSetServerUrlFromNative = value => { const next=String(value||'').trim().replace(/[/]+$/, ''); if(validServer(next)) server=next; };
          window.PortalNative = {
            getBuild: () => \(buildLiteral),
            getAppMetadata: () => metadata,
            getServerUrl: () => server,
            setServerUrl: value => {
              const next = String(value || '').trim().replace(/[/]+$/, '');
              if (!validServer(next)) return false;
              server = next; send('setServerUrl', {value:next}); return true;
            },
            setCacheCompany: value => {
              const next = String(value || '');
              cacheCompany = /^[1-9][0-9]{0,9}$/.test(next) ? next : '';
              send('setCacheCompany', {value:cacheCompany}); return !!cacheCompany;
            },
            clearCompanyCache: () => { send('clearCompanyCache', {}); return true; },
            openMessengerWindow: provider => { const p=String(provider||'telegram').toLowerCase()==='max'?'max':'telegram'; send('openMessengerWindow', {provider:p}); return true; },
            clearMessengerSession: () => { send('clearMessengerSession',{}); return true; },
            queueMutation: json => ask('queueMutation', {json:String(json||'')}),
            pendingMutations: () => ask('pendingMutations', {}).then(rows => JSON.stringify(Array.isArray(rows)?rows:[])),
            removeMutation: requestId => ask('removeMutation', {requestId:String(requestId||'')}),
            pendingMutationCount: () => ask('pendingMutationCount', {}),
            requestAsync: (id, method, path, body, token, company) =>
              send('requestAsync', {id:String(id), method:String(method||'GET'), path:String(path||''), body:String(body||''), token:String(token||''), company:String(company||'')}),
            request: () => JSON.stringify({ok:false,httpStatus:0,error:'Используйте requestAsync'}),
            requestForCompany: () => JSON.stringify({ok:false,httpStatus:0,error:'Используйте requestAsync'}),
            checkUpdates: id => send('checkUpdates', {id:String(id)}),
            downloadAndInstallUpdate: (id, manifest) => send('installUpdate', {id:String(id), manifest:String(manifest||'')}),
            saveBase64FileAsync: (id, name, mime, b64) =>
              send('saveFile', {id:String(id), name:String(name||''), mime:String(mime||''), b64:String(b64||'')}),
            shareBase64FileAsync: (id, name, mime, b64, recipient, subject, message) =>
              send('shareFile', {id:String(id), name:String(name||''), mime:String(mime||''), b64:String(b64||''), recipient:String(recipient||''), subject:String(subject||''), message:String(message||'')}),
            scheduleOrganizerReminders: json => send('scheduleOrganizerReminders', {json:String(json||'[]')})
          };
          window.__PORTAL_IOS__ = true;
          document.documentElement.classList.add('ios-client');
        })();
        """
    }

    func install(into controller: WKUserContentController) {
        userContentController = controller
        controller.add(self, name: Self.handlerName)
        controller.addScriptMessageHandler(self, contentWorld: .page, name: Self.replyHandlerName)
        controller.addUserScript(WKUserScript(source: bootstrapScript(), injectionTime: .atDocumentStart, forMainFrameOnly: true))
        activeObserver = NotificationCenter.default.addObserver(forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in
            self?.webView?.evaluateJavaScript("window.portalForegroundRefresh&&window.portalForegroundRefresh()")
        }
    }

    func detach() {
        if let activeObserver { NotificationCenter.default.removeObserver(activeObserver) }
        activeObserver = nil
        userContentController?.removeScriptMessageHandler(forName: Self.handlerName)
        userContentController?.removeScriptMessageHandler(forName: Self.replyHandlerName, contentWorld: .page)
        userContentController = nil
        webView = nil
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == Self.handlerName,
              let payload = message.body as? [String: Any],
              let action = payload["action"] as? String else { return }

        switch action {
        case "setServerUrl":
            if let value = payload["value"] as? String, Self.isValidServerURL(value) {
                defaults.set(value, forKey: "portal_server_url")
            }
        case "setCacheCompany":
            let value = payload["value"] as? String ?? ""
            cacheCompany = value.range(of: #"^[1-9][0-9]{0,9}$"#, options: .regularExpression) != nil ? value : ""
        case "clearCompanyCache":
            if !cacheCompany.isEmpty { _ = localCache.clearCompany(serverOrigin: serverURL, companyID: cacheCompany) }
        case "openMessengerWindow":
            let provider = (payload["provider"] as? String)?.lowercased() == "max" ? "max" : "telegram"
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                if self.messengerClearInProgress {
                    self.pendingMessengerProvider = provider
                    return
                }
                self.presentMessenger(provider)
            }
        case "clearMessengerSession":
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                if self.messengerClearInProgress {
                    self.pendingMessengerProvider = nil
                    return
                }
                self.messengerClearInProgress = true
                self.pendingMessengerProvider = nil
                MessengerViewController.clear { [weak self] in
                    DispatchQueue.main.async {
                        guard let self else { return }
                        let presenter = self.topViewController()
                        let current = (presenter as? MessengerViewController) ?? (presenter?.presentedViewController as? MessengerViewController)
                        let complete = {
                            self.messengerClearInProgress = false
                            if let pending = self.pendingMessengerProvider {
                                self.pendingMessengerProvider = nil
                                self.presentMessenger(pending)
                            }
                        }
                        if let current { current.dismiss(animated: false, completion: complete) }
                        else { complete() }
                    }
                }
            }
        case "scheduleOrganizerReminders":
            scheduleOrganizerReminders(payload["json"] as? String ?? "[]")
        case "requestAsync":
            request(payload)
        case "checkUpdates":
            let id = payload["id"] as? String
            refreshOfficialServer { [weak self] serverResult in
                var object: [String: Any] = [
                    "ok": true, "configured": false, "storeManaged": true, "platform": "ios"
                ]
                serverResult.forEach { object[$0.key] = $0.value }
                self?.deliver(id: id, object: object)
            }
        case "installUpdate":
            deliver(id: payload["id"] as? String, object: [
                "ok": false, "errorCode": "app_store_managed",
                "error": "Обновления iPhone устанавливаются через App Store по ссылке PORTAL."
            ])
        case "saveFile":
            saveFile(payload)
        case "shareFile":
            shareFile(payload)
        default:
            break
        }
    }

    private func presentMessenger(_ provider: String) {
        guard let presenter = topViewController() else { return }
        let current = (presenter as? MessengerViewController) ?? (presenter.presentedViewController as? MessengerViewController)
        if let current { current.selectProvider(provider); return }
        let messenger = MessengerViewController(provider: provider)
        messenger.modalPresentationStyle = .fullScreen
        presenter.present(messenger, animated: true)
    }

    private func scheduleOrganizerReminders(_ json: String) {
        guard let data = json.data(using: .utf8),
              let rows = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]], rows.count <= 50 else { return }
        let center = UNUserNotificationCenter.current()
        let prefix = "portal-organizer-"
        center.getPendingNotificationRequests { pending in
            center.removePendingNotificationRequests(withIdentifiers: pending.map(\.identifier).filter { $0.hasPrefix(prefix) })
            let now = Date()
            let upperBound = now.addingTimeInterval(30 * 24 * 60 * 60)
            let requests = rows.compactMap { row -> UNNotificationRequest? in
                guard let id = row["id"] as? String, id.range(of: #"^[A-Za-z0-9_-]{1,80}$"#, options: .regularExpression) != nil,
                      let value = row["at"] as? String else { return nil }
                let date = Self.organizerDate(from: value)
                guard let date, date > now, date < upperBound else { return nil }
                let content = UNMutableNotificationContent()
                content.title = "Напоминание PORTAL"
                content.body = String((row["title"] as? String ?? "Задача").prefix(160))
                content.sound = .default
                let trigger = UNCalendarNotificationTrigger(dateMatching: Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: date), repeats: false)
                return UNNotificationRequest(identifier: prefix + id, content: content, trigger: trigger)
            }
            guard !requests.isEmpty else { return }
            center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
                guard granted else { return }
                requests.forEach { center.add($0) { _ in } }
            }
        }
    }

    private static func organizerDate(from value: String) -> Date? {
        if let date = ISO8601DateFormatter().date(from: value) { return date }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        let local = DateFormatter()
        local.locale = Locale(identifier: "en_US_POSIX")
        local.timeZone = .current
        for format in ["yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd'T'HH:mm:ss"] {
            local.dateFormat = format
            if let date = local.date(from: value) { return date }
        }
        return nil
    }


    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.name == Self.replyHandlerName,
              let payload = message.body as? [String: Any],
              let action = payload["action"] as? String else {
            replyHandler(nil, "invalid_request")
            return
        }
        switch action {
        case "queueMutation":
            let raw = payload["json"] as? String ?? ""
            guard !cacheCompany.isEmpty, raw.utf8.count <= 512 * 1024,
                  let data = raw.data(using: .utf8),
                  let row = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  row["method"] as? String == "POST",
                  let mutationPath = row["path"] as? String, Self.localOutboxPaths.contains(mutationPath),
                  let requestID = row["request_id"] as? String,
                  requestID.range(of: #"^[0-9A-Fa-f-]{36}$"#, options: .regularExpression) != nil,
                  let body = row["body"] as? [String: Any],
                  body["request_id"] as? String == requestID else {
                replyHandler(false, nil)
                return
            }
            replyHandler(localCache.enqueueMutation(
                serverOrigin: serverURL, companyID: cacheCompany, requestID: requestID, json: raw
            ), nil)
        case "pendingMutations":
            guard !cacheCompany.isEmpty else { replyHandler([], nil); return }
            replyHandler(localCache.pendingMutations(serverOrigin: serverURL, companyID: cacheCompany), nil)
        case "removeMutation":
            let requestID = payload["requestId"] as? String ?? ""
            guard !cacheCompany.isEmpty else { replyHandler(false, nil); return }
            replyHandler(localCache.removeMutation(
                serverOrigin: serverURL, companyID: cacheCompany, requestID: requestID
            ), nil)
        case "pendingMutationCount":
            guard !cacheCompany.isEmpty else { replyHandler(0, nil); return }
            replyHandler(localCache.pendingMutationCount(serverOrigin: serverURL, companyID: cacheCompany), nil)
        default:
            replyHandler(nil, "unsupported_action")
        }
    }

    private func deliver(id: String?, object: [String: Any]) {
        guard let id, let webView else { return }
        let raw = Self.jsonObjectString(object)
        let script = "window.PortalBridgeResult(\(Self.jsonString(id)),\(Self.jsonString(raw)))"
        DispatchQueue.main.async {
            webView.evaluateJavaScript(script)
        }
    }

    private func refreshOfficialServer(completion: @escaping ([String: Any]) -> Void) {
        let channel = metadata["channel"] as? String ?? "development"
        guard channel == "release" else {
            completion(["serverChecked": false, "serverChanged": false, "serverUrl": serverURL])
            return
        }
        var request = URLRequest(url: Self.serverDiscoveryURL)
        request.httpMethod = "GET"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self else { return }
            guard error == nil,
                  let http = response as? HTTPURLResponse, http.statusCode == 200,
                  http.url == Self.serverDiscoveryURL,
                  let data, !data.isEmpty, data.count <= 16 * 1024,
                  let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  (object["schemaVersion"] as? NSNumber)?.intValue == 1,
                  let revisionValue = object["revision"] as? NSNumber, revisionValue.intValue >= 1,
                  let updatedAt = object["updatedAt"] as? String,
                  ISO8601DateFormatter().date(from: updatedAt) != nil,
                  let apiURL = object["apiUrl"] as? String,
                  let next = Self.normalizeOfficialServerURL(apiURL) else {
                completion(["serverChecked": false, "serverChanged": false, "serverUrl": self.serverURL])
                return
            }
            let revision = revisionValue.intValue
            let storedRevision = self.defaults.integer(forKey: "portal_server_discovery_revision")
            guard storedRevision <= revision else {
                completion(["serverChecked": false, "serverChanged": false, "serverUrl": self.serverURL])
                return
            }
            self.probeOfficialServer(next) { ready in
                guard ready else {
                    completion(["serverChecked": false, "serverChanged": false, "serverUrl": self.serverURL])
                    return
                }
                let previous = self.serverURL
                let changed = previous.caseInsensitiveCompare(next) != .orderedSame
                if changed && !self.localCache.migrateOutboxOrigin(oldOrigin: previous, newOrigin: next) {
                    completion(["serverChecked": false, "serverChanged": false, "serverUrl": previous])
                    return
                }
                self.defaults.set(next, forKey: "portal_server_url")
                self.defaults.set(revision, forKey: "portal_server_discovery_revision")
                if changed {
                    let script = "window.__portalSetServerUrlFromNative && window.__portalSetServerUrlFromNative(\(Self.jsonString(next)))"
                    DispatchQueue.main.async { self.webView?.evaluateJavaScript(script) }
                }
                completion(["serverChecked": true, "serverChanged": changed, "serverUrl": next])
            }
        }.resume()
    }

    private func probeOfficialServer(_ origin: String, completion: @escaping (Bool) -> Void) {
        guard let pingURL = URL(string: origin + "/api/ping") else { completion(false); return }
        var request = URLRequest(url: pingURL)
        request.httpMethod = "GET"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        URLSession.shared.dataTask(with: request) { data, response, error in
            guard error == nil,
                  let http = response as? HTTPURLResponse, http.statusCode == 200,
                  http.url == pingURL,
                  let data, data.count <= 32 * 1024,
                  let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  object["ok"] as? Bool == true,
                  let build = object["build"] as? String, build.hasPrefix("PORTAL Server") else {
                completion(false)
                return
            }
            completion(true)
        }.resume()
    }

    private func request(_ payload: [String: Any]) {
        guard let id = payload["id"] as? String,
              let path = payload["path"] as? String,
              path.hasPrefix("/api/"), !path.hasPrefix("//"),
              !path.contains("\\"), !path.contains("#") else {
            deliver(id: payload["id"] as? String, object: ["ok": false, "httpStatus": 0, "error": "Недопустимый API-запрос"])
            return
        }

        let method = (payload["method"] as? String ?? "GET").uppercased()
        guard ["GET", "POST"].contains(method),
              Self.isValidServerURL(serverURL),
              let url = URL(string: serverURL + path), url.scheme?.lowercased() == "https" || isLoopbackURL(url) else {
            deliver(id: id, object: ["ok": false, "httpStatus": 0, "error": "Недопустимый API-запрос"])
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("iOS", forHTTPHeaderField: "X-Portal-Client")

        let token = payload["token"] as? String ?? ""
        if !token.isEmpty, token.count <= 8192, !token.contains("\n"), !token.contains("\r") {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let company = payload["company"] as? String ?? ""
        if !company.isEmpty {
            guard let companyID = Int(company), companyID > 0 else {
                deliver(id: id, object: ["ok": false, "httpStatus": 0, "error": "Недопустимый контекст компании"])
                return
            }
            request.setValue(String(companyID), forHTTPHeaderField: "X-Portal-Company")
        }

        let body = payload["body"] as? String ?? ""
        if method == "POST", !body.isEmpty {
            guard body.utf8.count <= 24 * 1024 * 1024 else {
                deliver(id: id, object: ["ok": false, "httpStatus": 0, "error": "Недопустимые данные запроса"])
                return
            }
            request.httpBody = Data(body.utf8)
            request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        }

        let cacheOrigin = serverURL
        let cacheScope = cacheCompany
        let cacheEligible = method == "GET" && !token.isEmpty && !cacheScope.isEmpty && isCacheable(path)
        var cacheDelivered = false
        if cacheEligible, var cached = localCache.read(serverOrigin: cacheOrigin, companyID: cacheScope, cacheKey: path) {
            cached["cached"] = true
            deliver(id: id, object: cached)
            cacheDelivered = true
        }
        let didDeliverCached = cacheDelivered

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self else { return }
            if error != nil {
                if !didDeliverCached {
                    self.deliver(id: id, object: ["ok": false, "httpStatus": 0, "network": true, "error": "Не удалось связаться с сервером. Проверьте подключение."])
                }
                return
            }

            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let limit = path.hasPrefix("/api/v3/document-file") ? 30 * 1024 * 1024 :
                (path.hasPrefix("/api/v3/chat-file") ? 4 * 1024 * 1024 : 2 * 1024 * 1024)
            guard let data, data.count <= limit,
                  var object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
                if !didDeliverCached {
                    self.deliver(id: id, object: ["ok": false, "httpStatus": status, "error": "Сервер вернул некорректный ответ"])
                }
                return
            }
            object["httpStatus"] = status
            if cacheEligible {
                if (200..<300).contains(status), object["ok"] as? Bool != false {
                    _ = self.localCache.write(serverOrigin: cacheOrigin, companyID: cacheScope, cacheKey: path, object: object)
                } else if status == 401 || status == 403 {
                    _ = self.localCache.clearCompany(serverOrigin: cacheOrigin, companyID: cacheScope)
                }
            }
            if method == "POST", (200..<300).contains(status), object["ok"] as? Bool != false, !cacheScope.isEmpty {
                self.invalidateCache(serverOrigin: cacheOrigin, companyID: cacheScope, mutationPath: path)
            }
            if !didDeliverCached { self.deliver(id: id, object: object) }
        }.resume()
    }

    private func isLoopbackURL(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased(), scheme == "http",
              let host = url.host?.lowercased() else { return false }
        return Self.isLoopbackHost(host)
    }

    private func invalidateCache(serverOrigin: String, companyID: String, mutationPath: String) {
        let keys: [String]
        if mutationPath.range(of: #"^/api/v3/work(?:\?.*)?$"#, options: .regularExpression) != nil {
            keys = ["/api/v3/today","/api/v3/tasks","/api/v3/timers","/api/v3/finance","/api/v3/analytics","/api/v3/invoices","/api/v3/receivables"]
        } else if mutationPath.range(of: #"^/api/v3/links(?:\?.*)?$"#, options: .regularExpression) != nil {
            keys = ["/api/v3/today","/api/v3/tasks","/api/v3/batches","/api/v3/finance","/api/v3/analytics","/api/v3/invoices","/api/v3/receivables"]
        } else if mutationPath.range(of: #"^/api/v3/(?:batches|tasks)(?:\?.*)?$"#, options: .regularExpression) != nil {
            keys = ["/api/v3/today","/api/v3/tasks","/api/v3/timers","/api/v3/batches","/api/v3/finance","/api/v3/analytics"]
        } else if mutationPath.range(of: #"^/api/v3/(?:shipments|returns)(?:\?.*)?$"#, options: .regularExpression) != nil {
            keys = ["/api/v3/today","/api/v3/tasks","/api/v3/batches","/api/v3/finance","/api/v3/analytics","/api/v3/invoices","/api/v3/receivables"]
        } else if mutationPath.range(of: #"/(?:tariffs?|operations?|products?)(?:/|\?|$)"#, options: .regularExpression) != nil {
            keys = ["/api/v3/catalog","/api/v3/tariff-history","/api/v3/products","/api/v3/today","/api/v3/finance","/api/v3/analytics"]
        } else if mutationPath.range(of: #"/clients?(?:/|\?|$)"#, options: .regularExpression) != nil {
            keys = ["/api/clients","/api/admin/clients","/api/v3/catalog","/api/v3/client-name-history","/api/v3/client-requisites","/api/v3/today","/api/v3/finance","/api/v3/analytics"]
        } else if mutationPath.range(of: #"/materials?(?:/|\?|$)"#, options: .regularExpression) != nil {
            keys = ["/api/materials","/api/v3/today","/api/v3/finance","/api/v3/analytics"]
        } else if mutationPath.range(of: #"/(?:users?|invitations?|company-access|permissions)(?:/|\?|$)"#, options: .regularExpression) != nil {
            keys = ["/api/users","/api/v3/permissions","/api/v3/chat-users"]
        } else if mutationPath.range(of: #"/(?:invoices?|payments?)(?:/|\?|$)"#, options: .regularExpression) != nil {
            keys = ["/api/v3/invoices","/api/v3/receivables","/api/v3/finance","/api/v3/today"]
        } else if mutationPath.range(of: #"/settings(?:/|\?|$)"#, options: .regularExpression) != nil {
            keys = ["/api/company","/api/v3/settings","/api/v3/today"]
        } else {
            return
        }
        for key in keys {
            _ = localCache.delete(serverOrigin: serverOrigin, companyID: companyID, cacheKey: key)
        }
    }

    private func isCacheable(_ path: String) -> Bool {
        let patterns = [
            #"^/api/company$"#,
            #"^/api/(?:admin/)?clients(?:\?.*)?$"#,
            #"^/api/clients/[0-9]+(?:/operations)?(?:\?.*)?$"#,
            #"^/api/admin/clients/[0-9]+/operations(?:\?.*)?$"#,
            #"^/api/(?:users|materials|jobs)(?:\?.*)?$"#,
            #"^/api/v3/(?:catalog|products|client-requisites|client-name-history|tariff-history|today|tasks|timers|batches|invoices|receivables|finance|analytics|payroll-periods|documents|settings|permissions|chat-users)(?:\?.*)?$"#
        ]
        return patterns.contains { path.range(of: $0, options: .regularExpression) != nil }
    }
    private enum FileBridgeError: Error {
        case invalid
    }

    private func decodedFile(_ payload: [String: Any]) throws -> (id: String, name: String, mime: String, data: Data) {
        guard let id = payload["id"] as? String,
              let rawName = payload["name"] as? String,
              let mime = payload["mime"] as? String,
              let encoded = payload["b64"] as? String,
              encoded.count <= 28 * 1024 * 1024 else { throw FileBridgeError.invalid }

        let allowed: [String: [String]] = [
            "application/pdf": [".pdf"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
            "application/json": [".json"],
            "image/jpeg": [".jpg", ".jpeg"],
            "image/png": [".png"],
            "image/webp": [".webp"],
            "text/plain": [".txt"]
        ]
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard name.range(of: #"^[A-Za-z0-9._-]{1,120}$"#, options: .regularExpression) != nil,
              let suffixes = allowed[mime],
              suffixes.contains(where: { name.lowercased().hasSuffix($0) }),
              let data = Data(base64Encoded: encoded, options: .ignoreUnknownCharacters),
              !data.isEmpty, data.count <= 20 * 1024 * 1024 else { throw FileBridgeError.invalid }
        return (id, name, mime, data)
    }

    private func saveFile(_ payload: [String: Any]) {
        do {
            let file = try decodedFile(payload)
            let manager = FileManager.default
            let documents = try manager.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            let directory = documents.appendingPathComponent("PORTAL", isDirectory: true)
            try manager.createDirectory(at: directory, withIntermediateDirectories: true)
            let target = directory.appendingPathComponent(file.name)
            try file.data.write(to: target, options: .atomic)
            deliver(id: file.id, object: ["ok": true, "location": "Файлы/PORTAL/\(file.name)"])
        } catch {
            deliver(id: payload["id"] as? String, object: ["ok": false, "error": "Не удалось сохранить документ."])
        }
    }
    private func shareFile(_ payload: [String: Any]) {
        do {
            let file = try decodedFile(payload)
            let manager = FileManager.default
            let directory = manager.temporaryDirectory.appendingPathComponent("PORTALShare", isDirectory: true)
            try manager.createDirectory(at: directory, withIntermediateDirectories: true)
            let target = directory.appendingPathComponent("\(UUID().uuidString)_\(file.name)")
            try file.data.write(to: target, options: .atomic)

            DispatchQueue.main.async { [weak self] in
                guard let self, let presenter = self.topViewController() else {
                    self?.deliver(id: file.id, object: ["ok": false, "error": "Не удалось открыть системное меню отправки."])
                    return
                }
                var items: [Any] = [target]
                let message = (payload["message"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                if !message.isEmpty { items.append(String(message.prefix(2000))) }
                let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
                let subject = (payload["subject"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                if !subject.isEmpty { controller.setValue(String(subject.prefix(160)), forKey: "subject") }
                controller.completionWithItemsHandler = { _, completed, _, _ in
                    try? manager.removeItem(at: target)
                    self.deliver(id: file.id, object: completed
                        ? ["ok": true, "shared": true]
                        : ["ok": false, "cancelled": true, "error": "Отправка отменена"])
                }
                presenter.present(controller, animated: true)
            }
        } catch {
            deliver(id: payload["id"] as? String, object: ["ok": false, "error": "Не удалось подготовить документ."])
        }
    }

    private func topViewController() -> UIViewController? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        var controller = scenes.flatMap(\.windows).first(where: { $0.isKeyWindow })?.rootViewController
        while let presented = controller?.presentedViewController { controller = presented }
        return controller
    }
    func webView(_ webView: WKWebView,
                 decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.cancel)
            return
        }
        if url.isFileURL || url.scheme == "about" {
            decisionHandler(.allow)
            return
        }
        if Self.isAllowedExternalURL(url) {
            UIApplication.shared.open(url)
        }
        decisionHandler(.cancel)
    }
}
