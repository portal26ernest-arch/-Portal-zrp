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

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private WebView webView;

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

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new PortalBridge(this), "PortalNative");
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    public static class PortalBridge {
        private final Context context;
        private final SharedPreferences prefs;
        private static final String DEFAULT_URL = "http://127.0.0.1:8765";

        PortalBridge(Context context) {
            this.context = context;
            prefs = context.getSharedPreferences("portal_settings", Context.MODE_PRIVATE);
        }

        @JavascriptInterface
        public String getBuild() {
            return "PORTAL Android · Build " + BuildConfig.VERSION_NAME;
        }

        @JavascriptInterface
        public String getServerUrl() {
            return prefs.getString("server_url", DEFAULT_URL);
        }

        @JavascriptInterface
        public void setServerUrl(String value) {
            if (value == null) return;
            value = value.trim();
            while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
            if (!value.isEmpty()) prefs.edit().putString("server_url", value).apply();
        }

        @JavascriptInterface
        public String request(String method, String path, String body, String token) {
            HttpURLConnection conn = null;
            try {
                String base = getServerUrl();
                URL url = new URL(base + path);
                conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(15000);
                conn.setRequestMethod(method == null ? "GET" : method.toUpperCase());
                conn.setRequestProperty("Accept", "application/json");
                if (token != null && !token.isEmpty()) {
                    conn.setRequestProperty("Authorization", "Bearer " + token);
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
                StringBuilder sb = new StringBuilder();
                try (BufferedReader r = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = r.readLine()) != null) sb.append(line);
                }
                return sb.toString();
            } catch (Exception e) {
                String msg = e.getClass().getSimpleName() + ": " + (e.getMessage() == null ? "ошибка соединения" : e.getMessage());
                msg = msg.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ");
                return "{\"ok\":false,\"network\":true,\"error\":\"" + msg + "\"}";
            } finally {
                if (conn != null) conn.disconnect();
            }
        }
    }
}
