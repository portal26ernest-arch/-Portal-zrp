package ru.portal.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private WebView webView;
    private PortalBridge bridge;

    @SuppressLint({"SetJavaScriptEnabled", "JavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !request.getUrl().toString().startsWith("file:///android_asset/");
            }
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return !url.startsWith("file:///android_asset/");
            }
        });
        webView.setWebChromeClient(new WebChromeClient());
        bridge = new PortalBridge(this, webView);
        webView.addJavascriptInterface(bridge, "PortalNative");
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        webView.evaluateJavascript("window.portalBack ? window.portalBack() : false", value -> {
            if (!"true".equals(value)) MainActivity.super.onBackPressed();
        });
    }

    @Override
    protected void onDestroy() {
        if (bridge != null) bridge.close();
        if (webView != null) { webView.removeJavascriptInterface("PortalNative"); webView.destroy(); }
        super.onDestroy();
    }

    public static class PortalBridge {
        private final Context context;
        private final SharedPreferences prefs;
        private final WebView webView;
        private final ExecutorService executor = Executors.newFixedThreadPool(3);
        private volatile boolean closed;
        private static final String DEFAULT_URL = "http://127.0.0.1:8765";

        PortalBridge(Context context, WebView webView) {
            this.context = context;
            this.webView = webView;
            prefs = context.getSharedPreferences("portal_settings", Context.MODE_PRIVATE);
        }

        @JavascriptInterface
        public String getBuild() {
            return "PORTAL Android · Build " + BuildConfig.VERSION_NAME;
        }

        @JavascriptInterface
        public String getAppMetadata() {
            try {
                return new JSONObject().put("applicationId", BuildConfig.APPLICATION_ID)
                    .put("versionName", BuildConfig.VERSION_NAME).put("versionCode", BuildConfig.VERSION_CODE)
                    .put("buildNumber", BuildConfig.BUILD_NUMBER).put("buildDate", BuildConfig.BUILD_DATE)
                    .put("channel", BuildConfig.RELEASE_CHANNEL)
                    .put("updatesConfigured", !BuildConfig.UPDATE_MANIFEST_URL.isEmpty()).toString();
            } catch (Exception ignored) { return "{}"; }
        }

        private void deliver(String id, String result) {
            ((Activity) context).runOnUiThread(() -> {
                if (!closed) webView.evaluateJavascript("window.PortalBridgeResult(" + JSONObject.quote(id) + "," + JSONObject.quote(result) + ")", null);
            });
        }

        @JavascriptInterface
        public void requestAsync(String id, String method, String path, String body, String token, String company) {
            // Capture the server now, before queuing, so changing settings never
            // sends an old credential to the newly selected server.
            String base = getServerUrl();
            executor.execute(() -> deliver(id, requestAt(base, method, path, body, token, company)));
        }

        @JavascriptInterface
        public void checkUpdates(String id) {
            executor.execute(() -> deliver(id, fetchUpdateManifest()));
        }

        private String fetchUpdateManifest() {
            String source = BuildConfig.UPDATE_MANIFEST_URL;
            if (source.isEmpty()) return "{\"ok\":true,\"configured\":false}";
            HttpURLConnection conn = null;
            try {
                URL url = new URL(source);
                if (!"https".equals(url.getProtocol()) || url.getUserInfo() != null) throw new Exception();
                conn = (HttpURLConnection) url.openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(10000);
                conn.setRequestProperty("Accept", "application/json");
                conn.setRequestProperty("X-Portal-Client", "Android");
                // No Authorization, company headers, APK download or installation.
                if (conn.getResponseCode() != 200) throw new Exception();
                String raw = readLimited(conn.getInputStream(), 65536);
                return new JSONObject().put("ok", true).put("configured", true).put("manifest", new JSONObject(raw)).toString();
            } catch (Exception ignored) {
                return "{\"ok\":false,\"error\":\"Сервис обновлений недоступен. Повторите позже.\"}";
            } finally { if (conn != null) conn.disconnect(); }
        }

        private String readLimited(InputStream stream, int limit) throws Exception {
            try (InputStream input = stream; java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    if (out.size() + read > limit) throw new Exception("Ответ слишком большой");
                    out.write(buffer, 0, read);
                }
                return out.toString("UTF-8");
            }
        }

        void close() { closed = true; executor.shutdownNow(); }

        @JavascriptInterface
        public String getServerUrl() {
            return prefs.getString("server_url", DEFAULT_URL);
        }

        @JavascriptInterface
        public void setServerUrl(String value) {
            if (value == null) return;
            value = value.trim();
            while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
            try {
                URL url = new URL(value);
                if (("http".equals(url.getProtocol()) || "https".equals(url.getProtocol())) && url.getUserInfo() == null
                        && url.getQuery() == null && url.getRef() == null && (url.getPath().isEmpty() || "/".equals(url.getPath()))) {
                    prefs.edit().putString("server_url", value).apply();
                }
            } catch (Exception ignored) { }
        }

        @JavascriptInterface
        public String request(String method, String path, String body, String token) {
            return requestAt(getServerUrl(), method, path, body, token, "");
        }

        @JavascriptInterface
        public String requestForCompany(String method, String path, String body, String token, String company) {
            return requestAt(getServerUrl(), method, path, body, token, company);
        }

        private String requestAt(String base, String method, String path, String body, String token, String company) {
            HttpURLConnection conn = null;
            try {
                if (path == null || !path.startsWith("/api/") || path.contains("\\") || path.contains("#")) throw new Exception("Некорректный API-путь");
                URL url = new URL(base + path);
                conn = (HttpURLConnection) url.openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(15000);
                conn.setRequestMethod(method == null ? "GET" : method.toUpperCase());
                conn.setRequestProperty("Accept", "application/json");
                conn.setRequestProperty("X-Portal-Client", "Android");
                if (token != null && !token.isEmpty()) {
                    conn.setRequestProperty("Authorization", "Bearer " + token);
                }
                if (company != null && !company.isEmpty()) {
                    long companyId = Long.parseLong(company);
                    if (companyId < 1) throw new Exception("Некорректная компания");
                    conn.setRequestProperty("X-Portal-Company", Long.toString(companyId));
                }
                if (body != null && !body.isEmpty() && !"GET".equalsIgnoreCase(method)) {
                    conn.setDoOutput(true);
                    conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    byte[] data = body.getBytes(StandardCharsets.UTF_8);
                    conn.setFixedLengthStreamingMode(data.length);
                    try (OutputStream out = conn.getOutputStream()) { out.write(data); }
                }
                int code = conn.getResponseCode();
                InputStream stream = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
                if (stream == null) return "{\"ok\":false,\"error\":\"HTTP " + code + "\"}";
                JSONObject result = new JSONObject(readLimited(stream, 2 * 1024 * 1024));
                result.put("httpStatus", code);
                return result.toString();
            } catch (Exception e) {
                return "{\"ok\":false,\"network\":true,\"error\":\"Не удалось связаться с сервером. Проверьте подключение.\"}";
            } finally {
                if (conn != null) conn.disconnect();
            }
        }
    }
}
