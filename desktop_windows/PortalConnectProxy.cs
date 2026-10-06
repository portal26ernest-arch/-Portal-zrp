using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Portal.Desktop;

internal sealed class PortalConnectProxy : IDisposable
{
    private static readonly HashSet<string> AllowedHosts = new(StringComparer.OrdinalIgnoreCase)
    {
        "api.vart-portal.ru",
        "reserve-api.vart-portal.ru"
    };

    private const int MaxHeaderBytes = 16 * 1024;
    private readonly TcpListener _listener;
    private readonly CancellationTokenSource _stop = new();
    private readonly Task _acceptLoop;
    private int _disposed;

    private PortalConnectProxy(TcpListener listener)
    {
        _listener = listener;
        Port = ((IPEndPoint)listener.LocalEndpoint).Port;
        _acceptLoop = AcceptLoopAsync();
    }

    public int Port { get; }

    public string BrowserArguments =>
        $"--proxy-server=http://127.0.0.1:{Port} --proxy-bypass-list=<-loopback> --disable-quic --disable-http2";

    public static PortalConnectProxy Start()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start(32);
        return new PortalConnectProxy(listener);
    }

    private async Task AcceptLoopAsync()
    {
        while (!_stop.IsCancellationRequested)
        {
            TcpClient? client = null;
            try
            {
                client = await _listener.AcceptTcpClientAsync(_stop.Token);
                _ = HandleClientAsync(client);
            }
            catch (OperationCanceledException) when (_stop.IsCancellationRequested)
            {
                client?.Dispose();
                break;
            }
            catch (ObjectDisposedException) when (_stop.IsCancellationRequested)
            {
                client?.Dispose();
                break;
            }
            catch
            {
                client?.Dispose();
                if (_stop.IsCancellationRequested) break;
            }
        }
    }

    private async Task HandleClientAsync(TcpClient client)
    {
        using (client)
        {
            try
            {
                using var stream = client.GetStream();
                var header = await ReadHeaderAsync(stream, _stop.Token);
                if (!TryParseConnect(header, out var host))
                {
                    await WriteStatusAsync(stream, "405 Method Not Allowed", _stop.Token);
                    return;
                }

                if (!AllowedHosts.Contains(host))
                {
                    await WriteStatusAsync(stream, "403 Forbidden", _stop.Token);
                    return;
                }

                using var upstream = await ConnectIpv4Async(host, 443, _stop.Token);
                using var upstreamStream = upstream.GetStream();
                var established = Encoding.ASCII.GetBytes(
                    "HTTP/1.1 200 Connection Established\r\nProxy-Agent: PORTAL-Desktop\r\n\r\n");
                await stream.WriteAsync(established, _stop.Token);
                await stream.FlushAsync(_stop.Token);

                using var relayStop = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
                var toUpstream = stream.CopyToAsync(upstreamStream, relayStop.Token);
                var toClient = upstreamStream.CopyToAsync(stream, relayStop.Token);
                await Task.WhenAny(toUpstream, toClient);
                relayStop.Cancel();
                try { await Task.WhenAll(toUpstream, toClient); } catch { }
            }
            catch (OperationCanceledException) when (_stop.IsCancellationRequested) { }
            catch
            {
                try
                {
                    if (client.Connected)
                        await WriteStatusAsync(client.GetStream(), "502 Bad Gateway", CancellationToken.None);
                }
                catch { }
            }
        }
    }

    private static async Task<TcpClient> ConnectIpv4Async(string host, int port, CancellationToken cancellationToken)
    {
        var addresses = await Dns.GetHostAddressesAsync(host, cancellationToken);
        Exception? last = null;
        foreach (var address in addresses.Where(a => a.AddressFamily == AddressFamily.InterNetwork))
        {
            var tcp = new TcpClient(AddressFamily.InterNetwork);
            try
            {
                await tcp.ConnectAsync(address, port, cancellationToken);
                return tcp;
            }
            catch (Exception ex)
            {
                last = ex;
                tcp.Dispose();
            }
        }
        throw new IOException($"No reachable IPv4 address for {host}.", last);
    }

    private static async Task<string> ReadHeaderAsync(NetworkStream stream, CancellationToken cancellationToken)
    {
        var buffer = new byte[1024];
        using var data = new MemoryStream();
        while (data.Length < MaxHeaderBytes)
        {
            var read = await stream.ReadAsync(buffer, cancellationToken);
            if (read <= 0) break;
            data.Write(buffer, 0, read);
            var bytes = data.GetBuffer();
            var count = (int)data.Length;
            if (count >= 4 &&
                bytes[count - 4] == 13 && bytes[count - 3] == 10 &&
                bytes[count - 2] == 13 && bytes[count - 1] == 10)
                break;
        }

        if (data.Length == 0 || data.Length >= MaxHeaderBytes)
            return string.Empty;
        return Encoding.ASCII.GetString(data.GetBuffer(), 0, (int)data.Length);
    }

    private static bool TryParseConnect(string header, out string host)
    {
        host = string.Empty;
        var firstLineEnd = header.IndexOf("\r\n", StringComparison.Ordinal);
        if (firstLineEnd <= 0) return false;
        var parts = header[..firstLineEnd].Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length != 3 ||
            !parts[0].Equals("CONNECT", StringComparison.OrdinalIgnoreCase) ||
            !parts[2].StartsWith("HTTP/1.", StringComparison.OrdinalIgnoreCase))
            return false;

        var authority = parts[1];
        var colon = authority.LastIndexOf(':');
        if (colon <= 0 || !int.TryParse(authority[(colon + 1)..], out var port) || port != 443)
            return false;
        host = authority[..colon].Trim().TrimEnd('.');
        return host.Length > 0 && host.IndexOfAny(new[] { '/', '\\', '@', '[', ']' }) < 0;
    }

    private static async Task WriteStatusAsync(NetworkStream stream, string status, CancellationToken cancellationToken)
    {
        var bytes = Encoding.ASCII.GetBytes($"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        await stream.WriteAsync(bytes, cancellationToken);
        await stream.FlushAsync(cancellationToken);
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
        _stop.Cancel();
        try { _listener.Stop(); } catch { }
        _stop.Dispose();
    }
}
