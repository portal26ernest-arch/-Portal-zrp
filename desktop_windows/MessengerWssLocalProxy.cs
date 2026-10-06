using System.Net;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text;

namespace Portal.Desktop;

/// <summary>
/// Loopback-only HTTP CONNECT bridge for the Telegram WebView2 profile.
/// It accepts only Telegram:443 and carries the untouched provider TLS stream
/// inside an authenticated WSS connection. Relay credentials never enter URLs.
/// </summary>
internal sealed class MessengerWssLocalProxy : IDisposable
{
    private const int MaxHeaderBytes = 16 * 1024;
    private readonly MessengerRelayTicket _ticket;
    private readonly TcpListener _listener;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _acceptLoop;
    private bool _disposed;

    private MessengerWssLocalProxy(MessengerRelayTicket ticket)
    {
        _ticket = ticket;
        _listener = new TcpListener(IPAddress.Loopback, 0);
        _listener.Start(16);
        _acceptLoop = AcceptLoopAsync();
    }

    internal static MessengerWssLocalProxy Start(MessengerRelayTicket ticket)
    {
        if (!ticket.HasWssTransport || !Uri.TryCreate(ticket.WssUrl, UriKind.Absolute, out var uri) ||
            uri.Scheme != "wss" || string.IsNullOrWhiteSpace(uri.Host) || !string.IsNullOrEmpty(uri.UserInfo) ||
            uri.Port != 443 || uri.AbsolutePath != "/connect" || !string.IsNullOrEmpty(uri.Query) ||
            !string.IsNullOrEmpty(uri.Fragment))
            throw new InvalidOperationException("Invalid PORTAL Messenger WSS relay ticket.");
        return new MessengerWssLocalProxy(ticket);
    }

    internal string ProxyUrl
    {
        get
        {
            var endpoint = (IPEndPoint)_listener.LocalEndpoint;
            return $"http://127.0.0.1:{endpoint.Port}";
        }
    }

    private async Task AcceptLoopAsync()
    {
        while (!_shutdown.IsCancellationRequested)
        {
            TcpClient? client = null;
            try
            {
                client = await _listener.AcceptTcpClientAsync(_shutdown.Token);
                _ = Task.Run(() => HandleClientAsync(client, _shutdown.Token));
            }
            catch (OperationCanceledException) { client?.Dispose(); break; }
            catch (ObjectDisposedException) { client?.Dispose(); break; }
            catch { client?.Dispose(); if (_shutdown.IsCancellationRequested) break; }
        }
    }

    private async Task HandleClientAsync(TcpClient client, CancellationToken shutdown)
    {
        using var clientResource = client;
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(shutdown);
        linked.CancelAfter(TimeSpan.FromSeconds(15));
        var stream = client.GetStream();
        var target = await ReadConnectTargetAsync(stream, linked.Token);
        if (target is null)
        {
            await ReplyAsync(stream, "400 Bad Request", linked.Token);
            return;
        }
        var separator = target.LastIndexOf(':');
        var host = target[..separator].ToLowerInvariant();
        if (!AllowedHost(host) || !target.EndsWith(":443", StringComparison.Ordinal))
        {
            await ReplyAsync(stream, "403 Forbidden", linked.Token);
            return;
        }

        using var webSocket = new ClientWebSocket();
        webSocket.Options.KeepAliveInterval = TimeSpan.FromSeconds(30);
        var token = Convert.ToBase64String(Encoding.UTF8.GetBytes($"{_ticket.UserName}:{_ticket.Password}"));
        webSocket.Options.SetRequestHeader("Authorization", "Basic " + token);
        webSocket.Options.SetRequestHeader("X-Portal-Target", host + ":443");
        try
        {
            await webSocket.ConnectAsync(new Uri(_ticket.WssUrl), linked.Token);
        }
        catch
        {
            await ReplyAsync(stream, "502 Bad Gateway", CancellationToken.None);
            return;
        }

        linked.CancelAfter(Timeout.InfiniteTimeSpan);
        await stream.WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 200 Connection Established\r\nProxy-Agent: PORTAL-WSS\r\n\r\n"), linked.Token);
        await stream.FlushAsync(linked.Token);

        using var tunnel = CancellationTokenSource.CreateLinkedTokenSource(shutdown);
        var toRelay = PumpTcpToWebSocketAsync(stream, webSocket, tunnel.Token);
        var fromRelay = PumpWebSocketToTcpAsync(webSocket, stream, tunnel.Token);
        await Task.WhenAny(toRelay, fromRelay);
        tunnel.Cancel();
        try { await Task.WhenAll(toRelay, fromRelay); } catch { }
        try
        {
            if (webSocket.State is WebSocketState.Open or WebSocketState.CloseReceived)
                await webSocket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);
        }
        catch { }
    }

    private static async Task PumpTcpToWebSocketAsync(NetworkStream stream, ClientWebSocket webSocket, CancellationToken cancellationToken)
    {
        var buffer = new byte[32 * 1024];
        while (!cancellationToken.IsCancellationRequested)
        {
            var count = await stream.ReadAsync(buffer, cancellationToken);
            if (count <= 0) return;
            await webSocket.SendAsync(buffer.AsMemory(0, count), WebSocketMessageType.Binary, true, cancellationToken);
        }
    }

    private static async Task PumpWebSocketToTcpAsync(ClientWebSocket webSocket, NetworkStream stream, CancellationToken cancellationToken)
    {
        var buffer = new byte[64 * 1024];
        while (!cancellationToken.IsCancellationRequested)
        {
            var result = await webSocket.ReceiveAsync(buffer, cancellationToken);
            if (result.MessageType == WebSocketMessageType.Close) return;
            if (result.MessageType != WebSocketMessageType.Binary)
                throw new IOException("PORTAL WSS relay sent a non-binary frame.");
            if (result.Count > 0)
            {
                await stream.WriteAsync(buffer.AsMemory(0, result.Count), cancellationToken);
                await stream.FlushAsync(cancellationToken);
            }
        }
    }

    private static async Task<string?> ReadConnectTargetAsync(NetworkStream stream, CancellationToken cancellationToken)
    {
        var bytes = new List<byte>(1024);
        var state = 0;
        var one = new byte[1];
        while (bytes.Count < MaxHeaderBytes)
        {
            if (await stream.ReadAsync(one, cancellationToken) != 1) return null;
            var value = one[0];
            bytes.Add(value);
            if ((state == 0 || state == 2) && value == (byte)'\r') state++;
            else if ((state == 1 || state == 3) && value == (byte)'\n') state++;
            else state = value == (byte)'\r' ? 1 : 0;
            if (state == 4) break;
        }
        if (state != 4) return null;
        var raw = Encoding.Latin1.GetString(bytes.ToArray());
        var lineEnd = raw.IndexOf("\r\n", StringComparison.Ordinal);
        if (lineEnd <= 0) return null;
        var parts = raw[..lineEnd].Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length != 3 || !parts[0].Equals("CONNECT", StringComparison.OrdinalIgnoreCase) ||
            !parts[2].StartsWith("HTTP/1.", StringComparison.Ordinal))
            return null;
        var target = parts[1];
        var separator = target.LastIndexOf(':');
        if (separator <= 0 || separator == target.Length - 1 || target.Any(char.IsWhiteSpace)) return null;
        return int.TryParse(target[(separator + 1)..], out var port) && port == 443 ? target : null;
    }

    internal static bool AllowedHost(string? host)
    {
        if (string.IsNullOrWhiteSpace(host)) return false;
        var value = host.ToLowerInvariant();
        return value == "telegram.org" || value.EndsWith(".telegram.org", StringComparison.Ordinal) ||
               value == "t.me" || value.EndsWith(".t.me", StringComparison.Ordinal);
    }

    private static async Task ReplyAsync(NetworkStream stream, string status, CancellationToken cancellationToken)
    {
        try
        {
            var bytes = Encoding.ASCII.GetBytes($"HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
            await stream.WriteAsync(bytes, cancellationToken);
            await stream.FlushAsync(cancellationToken);
        }
        catch { }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _shutdown.Cancel();
        _listener.Stop();
        try { _acceptLoop.Wait(TimeSpan.FromSeconds(1)); } catch { }
        _shutdown.Dispose();
    }
}
