package ru.portal.app;

import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import okio.ByteString;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * Loopback-only CONNECT bridge used by the isolated Messenger process.
 *
 * WebView sees a local HTTP proxy.  The bridge validates Telegram:443, then
 * carries the untouched provider TLS bytes inside authenticated WSS.  Relay
 * credentials never enter the provider URL or WebView.
 */
final class TelegramWssLocalProxy implements Closeable {
    private static final int MAX_HEADER = 16 * 1024;
    private static final int CONNECT_TIMEOUT_SECONDS = 15;
    private final URI wssUri;
    private final String username;
    private final String password;
    private final ServerSocket listener;
    private final ExecutorService workers = Executors.newFixedThreadPool(8);
    private final OkHttpClient client;
    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final Thread acceptThread;

    private TelegramWssLocalProxy(URI wssUri, String username, String password) throws IOException {
        this.wssUri = wssUri;
        this.username = username;
        this.password = password;
        this.listener = new ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"));
        this.client = new OkHttpClient.Builder()
                .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .pingInterval(30, TimeUnit.SECONDS)
                .build();
        this.acceptThread = new Thread(this::acceptLoop, "portal-telegram-wss-accept");
        this.acceptThread.setDaemon(true);
        this.acceptThread.start();
    }

    static TelegramWssLocalProxy start(String rawUrl, String username, String password) throws Exception {
        URI uri = URI.create(rawUrl);
        if (!"wss".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null ||
                uri.getQuery() != null || uri.getFragment() != null || !"/connect".equals(uri.getPath()) ||
                (uri.getPort() != -1 && uri.getPort() != 443) ||
                username == null || username.isEmpty() || username.length() > 256 ||
                password == null || password.isEmpty() || password.length() > 256) {
            throw new IllegalArgumentException("invalid PORTAL WSS relay ticket");
        }
        return new TelegramWssLocalProxy(uri, username, password);
    }

    String proxyUrl() {
        return "http://127.0.0.1:" + listener.getLocalPort();
    }

    private void acceptLoop() {
        while (!closed.get()) {
            try {
                Socket socket = listener.accept();
                if (closed.get()) {
                    socket.close();
                    break;
                }
                workers.execute(() -> handle(socket));
            } catch (IOException ignored) {
                if (!closed.get()) closeQuietly();
            }
        }
    }

    private void handle(Socket socket) {
        WebSocket webSocket = null;
        try (socket) {
            socket.setSoTimeout(CONNECT_TIMEOUT_SECONDS * 1000);
            InputStream input = socket.getInputStream();
            OutputStream output = socket.getOutputStream();
            String target = readConnectTarget(input);
            if (target == null) {
                reply(output, "400 Bad Request");
                return;
            }
            String host = target.substring(0, target.lastIndexOf(':')).toLowerCase(Locale.ROOT);
            if (!allowedHost(host) || !target.endsWith(":443")) {
                reply(output, "403 Forbidden");
                return;
            }

            CountDownLatch ready = new CountDownLatch(1);
            AtomicBoolean opened = new AtomicBoolean(false);
            Object outputLock = new Object();
            String token = Base64.encodeToString((username + ":" + password).getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
            Request request = new Request.Builder()
                    .url(wssUri.toString())
                    .header("Authorization", "Basic " + token)
                    .header("X-Portal-Target", host + ":443")
                    .build();
            WebSocketListener bridge = new WebSocketListener() {
                @Override public void onOpen(WebSocket ws, Response response) {
                    opened.set(true);
                    ready.countDown();
                }

                @Override public void onMessage(WebSocket ws, ByteString bytes) {
                    try {
                        synchronized (outputLock) {
                            output.write(bytes.toByteArray());
                            output.flush();
                        }
                    } catch (IOException ignored) {
                        ws.cancel();
                    }
                }

                @Override public void onMessage(WebSocket ws, String text) {
                    ws.close(1003, "binary only");
                }

                @Override public void onClosing(WebSocket ws, int code, String reason) {
                    ws.close(code, null);
                }

                @Override public void onClosed(WebSocket ws, int code, String reason) {
                    try { socket.close(); } catch (IOException ignored) { }
                }

                @Override public void onFailure(WebSocket ws, Throwable t, Response response) {
                    ready.countDown();
                    try { socket.close(); } catch (IOException ignored) { }
                }
            };
            webSocket = client.newWebSocket(request, bridge);
            if (!ready.await(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS) || !opened.get()) {
                if (!socket.isClosed()) reply(output, "502 Bad Gateway");
                webSocket.cancel();
                return;
            }

            synchronized (outputLock) {
                output.write("HTTP/1.1 200 Connection Established\r\nProxy-Agent: PORTAL-WSS\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
                output.flush();
            }
            socket.setSoTimeout(0);
            byte[] buffer = new byte[32 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                if (count == 0) continue;
                if (!webSocket.send(ByteString.of(buffer, 0, count))) break;
            }
            webSocket.close(1000, null);
        } catch (Exception ignored) {
            if (webSocket != null) webSocket.cancel();
        }
    }

    private static String readConnectTarget(InputStream input) throws IOException {
        ByteArrayOutputStream head = new ByteArrayOutputStream();
        int state = 0;
        while (head.size() < MAX_HEADER) {
            int value = input.read();
            if (value < 0) return null;
            head.write(value);
            if ((state == 0 || state == 2) && value == '\r') state++;
            else if ((state == 1 || state == 3) && value == '\n') state++;
            else state = value == '\r' ? 1 : 0;
            if (state == 4) break;
        }
        if (state != 4) return null;
        String raw = head.toString(StandardCharsets.ISO_8859_1);
        int lineEnd = raw.indexOf("\r\n");
        if (lineEnd <= 0) return null;
        String[] parts = raw.substring(0, lineEnd).split(" ");
        if (parts.length != 3 || !"CONNECT".equalsIgnoreCase(parts[0]) || !parts[2].startsWith("HTTP/1.")) return null;
        String target = parts[1];
        int separator = target.lastIndexOf(':');
        if (separator <= 0 || separator == target.length() - 1 || target.indexOf(' ') >= 0 || target.indexOf('\t') >= 0) return null;
        try {
            if (Integer.parseInt(target.substring(separator + 1)) != 443) return null;
        } catch (NumberFormatException ignored) {
            return null;
        }
        return target;
    }

    static boolean allowedHost(String host) {
        if (host == null) return false;
        String value = host.toLowerCase(Locale.ROOT);
        return value.equals("telegram.org") || value.endsWith(".telegram.org") ||
                value.equals("t.me") || value.endsWith(".t.me");
    }

    private static void reply(OutputStream output, String status) {
        try {
            output.write(("HTTP/1.1 " + status + "\r\nConnection: close\r\nContent-Length: 0\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
            output.flush();
        } catch (IOException ignored) { }
    }

    private void closeQuietly() {
        try { listener.close(); } catch (IOException ignored) { }
    }

    @Override public void close() {
        if (!closed.compareAndSet(false, true)) return;
        closeQuietly();
        workers.shutdownNow();
        client.dispatcher().executorService().shutdown();
        client.connectionPool().evictAll();
    }
}
