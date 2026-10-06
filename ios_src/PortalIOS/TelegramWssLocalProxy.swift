import Foundation
import Network

/// Loopback-only CONNECT bridge for Telegram inside the isolated Messenger WKWebView.
/// The local listener accepts only Telegram:443 and carries provider TLS bytes over
/// authenticated WSS. Relay credentials are HTTP headers and never URL components.
final class TelegramWssLocalProxy {
    private let listener: NWListener
    private let queue = DispatchQueue(label: "ru.portal.messenger.wss-listener")
    private let lock = NSLock()
    private var tunnels: [UUID: Tunnel] = [:]
    let port: UInt16

    init(wssURL: String, username: String, password: String) throws {
        guard let url = URL(string: wssURL), url.scheme?.lowercased() == "wss",
              url.host != nil, url.user == nil, url.password == nil,
              url.port == nil || url.port == 443, url.path == "/connect",
              url.query == nil, url.fragment == nil,
              !username.isEmpty, username.count <= 256,
              !password.isEmpty, password.count <= 256 else {
            throw ProxyError.invalidTicket
        }

        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(
            host: NWEndpoint.Host("127.0.0.1"),
            port: NWEndpoint.Port(rawValue: 0)!
        )
        parameters.allowLocalEndpointReuse = false
        listener = try NWListener(using: parameters)

        let ready = DispatchSemaphore(value: 0)
        var failed = false
        listener.stateUpdateHandler = { state in
            switch state {
            case .ready:
                ready.signal()
            case .failed, .cancelled:
                failed = true
                ready.signal()
            default:
                break
            }
        }
        listener.start(queue: queue)
        guard ready.wait(timeout: .now() + 3) == .success, !failed, let boundPort = listener.port else {
            listener.cancel()
            throw ProxyError.listenerUnavailable
        }
        port = boundPort.rawValue

        listener.newConnectionHandler = { [weak self] connection in
            guard let self else { connection.cancel(); return }
            guard Self.isLoopback(connection.endpoint) else { connection.cancel(); return }
            let id = UUID()
            let tunnel = Tunnel(
                connection: connection,
                wssURL: url,
                username: username,
                password: password,
                onClose: { [weak self] in self?.removeTunnel(id) }
            )
            self.lock.lock()
            self.tunnels[id] = tunnel
            self.lock.unlock()
            tunnel.start()
        }
    }

    var proxyHost: String { "127.0.0.1" }

    deinit { close() }

    func close() {
        listener.cancel()
        lock.lock()
        let active = Array(tunnels.values)
        tunnels.removeAll()
        lock.unlock()
        active.forEach { $0.close() }
    }

    private func removeTunnel(_ id: UUID) {
        lock.lock()
        tunnels.removeValue(forKey: id)
        lock.unlock()
    }

    private static func isLoopback(_ endpoint: NWEndpoint) -> Bool {
        guard case let .hostPort(host, _) = endpoint else { return false }
        let value = String(describing: host).lowercased()
        return value == "127.0.0.1" || value == "::1" || value == "[::1]" || value == "localhost"
    }

    static func allowedHost(_ host: String) -> Bool {
        let value = host.lowercased()
        return value == "telegram.org" || value.hasSuffix(".telegram.org") ||
            value == "t.me" || value.hasSuffix(".t.me")
    }

    private enum ProxyError: Error {
        case invalidTicket
        case listenerUnavailable
    }

    private final class Tunnel: NSObject, URLSessionWebSocketDelegate {
        private let connection: NWConnection
        private let wssURL: URL
        private let username: String
        private let password: String
        private let onClose: () -> Void
        private let queue = DispatchQueue(label: "ru.portal.messenger.wss-tunnel")
        private var header = Data()
        private var session: URLSession?
        private var webSocket: URLSessionWebSocketTask?
        private var opened = false
        private var closed = false

        init(connection: NWConnection, wssURL: URL, username: String, password: String, onClose: @escaping () -> Void) {
            self.connection = connection
            self.wssURL = wssURL
            self.username = username
            self.password = password
            self.onClose = onClose
            super.init()
        }

        func start() {
            connection.stateUpdateHandler = { [weak self] state in
                if case .failed = state { self?.close() }
                if case .cancelled = state { self?.close() }
            }
            connection.start(queue: queue)
            readHeader()
        }

        private func readHeader() {
            connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, complete, error in
                guard let self, !self.closed else { return }
                if let data { self.header.append(data) }
                if self.header.count > 16 * 1024 {
                    self.replyAndClose("431 Request Header Fields Too Large")
                    return
                }
                if let range = self.header.range(of: Data("\r\n\r\n".utf8)) {
                    let head = self.header.prefix(upTo: range.upperBound)
                    guard let target = Self.connectTarget(Data(head)) else {
                        self.replyAndClose("400 Bad Request")
                        return
                    }
                    let parts = target.split(separator: ":", maxSplits: 1).map(String.init)
                    guard parts.count == 2, parts[1] == "443", TelegramWssLocalProxy.allowedHost(parts[0]) else {
                        self.replyAndClose("403 Forbidden")
                        return
                    }
                    self.openWebSocket(targetHost: parts[0].lowercased())
                    return
                }
                if complete || error != nil {
                    self.close()
                    return
                }
                self.readHeader()
            }
        }

        private static func connectTarget(_ data: Data) -> String? {
            guard let text = String(data: data, encoding: .isoLatin1),
                  let first = text.components(separatedBy: "\r\n").first else { return nil }
            let pieces = first.split(separator: " ", omittingEmptySubsequences: true)
            guard pieces.count == 3, pieces[0].uppercased() == "CONNECT",
                  pieces[2].hasPrefix("HTTP/1.") else { return nil }
            let target = String(pieces[1])
            guard !target.contains(where: { $0.isWhitespace }),
                  let separator = target.lastIndex(of: ":"),
                  Int(target[target.index(after: separator)...]) == 443 else { return nil }
            return target
        }

        private func openWebSocket(targetHost: String) {
            var request = URLRequest(url: wssURL)
            let auth = Data("\(username):\(password)".utf8).base64EncodedString()
            request.setValue("Basic \(auth)", forHTTPHeaderField: "Authorization")
            request.setValue("\(targetHost):443", forHTTPHeaderField: "X-Portal-Target")
            request.timeoutInterval = 15
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 20
            configuration.timeoutIntervalForResource = 0
            let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
            self.session = session
            let task = session.webSocketTask(with: request)
            self.webSocket = task
            task.resume()
        }

        func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                        didOpenWithProtocol protocol: String?) {
            opened = true
            let response = Data("HTTP/1.1 200 Connection Established\r\nProxy-Agent: PORTAL-WSS\r\n\r\n".utf8)
            connection.send(content: response, completion: .contentProcessed { [weak self] error in
                guard let self, error == nil else { self?.close(); return }
                self.readLocal()
                self.readWebSocket()
            })
        }

        func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
            close()
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            guard error != nil, !closed else { return }
            if opened { close() } else { replyAndClose("502 Bad Gateway") }
        }

        private func readLocal() {
            connection.receive(minimumIncompleteLength: 1, maximumLength: 32 * 1024) { [weak self] data, _, complete, error in
                guard let self, !self.closed else { return }
                guard error == nil else { self.close(); return }
                if let data, !data.isEmpty {
                    self.webSocket?.send(.data(data)) { [weak self] error in
                        guard let self else { return }
                        if error != nil { self.close() }
                        else if complete { self.close() }
                        else { self.readLocal() }
                    }
                } else if complete {
                    self.close()
                } else {
                    self.readLocal()
                }
            }
        }

        private func readWebSocket() {
            webSocket?.receive { [weak self] result in
                guard let self, !self.closed else { return }
                switch result {
                case .failure:
                    self.close()
                case .success(let message):
                    guard case .data(let data) = message else {
                        self.webSocket?.cancel(with: .unsupportedData, reason: nil)
                        self.close()
                        return
                    }
                    self.connection.send(content: data, completion: .contentProcessed { [weak self] error in
                        guard let self else { return }
                        if error != nil { self.close() } else { self.readWebSocket() }
                    })
                }
            }
        }

        private func replyAndClose(_ status: String) {
            let data = Data("HTTP/1.1 \(status)\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".utf8)
            connection.send(content: data, completion: .contentProcessed { [weak self] _ in self?.close() })
        }

        func close() {
            guard !closed else { return }
            closed = true
            webSocket?.cancel(with: .goingAway, reason: nil)
            connection.cancel()
            session?.invalidateAndCancel()
            session = nil
            webSocket = nil
            onClose()
        }
    }
}
