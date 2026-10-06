package ru.portal.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.HttpAuthHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.content.ContextCompat;
import androidx.webkit.ProxyConfig;
import androidx.webkit.ProxyController;
import androidx.webkit.WebViewFeature;

import org.json.JSONObject;

import java.net.URI;
import java.time.Instant;

/**
 * Device-local Telegram + MAX container.
 *
 * The PORTAL Relay is process-scoped and applies only to this dedicated :messenger
 * WebView process. It never changes Android's system VPN/proxy settings and it never
 * receives the PORTAL login token or provider cookies from the main PORTAL WebView.
 */
public final class MessengerActivity extends Activity {
    static final String TELEGRAM_URL = "https://web.telegram.org/a/";
    static final String MAX_URL = "https://web.max.ru/";
    static final String ACTION_CLEAR_SESSION = "ru.portal.app.action.CLEAR_MESSENGER_SESSION";
    private static boolean dataDirectorySuffixConfigured;
    private WebView browser;
    private boolean clearingSession;
    private String pendingProvider;
    private String pendingRelay;
    private Button telegram;
    private Button max;
    private Button relayButton;
    private TextView status;
    private String provider = "telegram";
    private boolean relayActive;
    private String relayProxyUrl = "";
    private String relayHost = "";
    private String relayUser = "";
    private String relayPassword = "";
    private String relayRealm = "PORTAL Messenger Relay";
    private boolean relayRequired = true;

    public static boolean isAllowedTopLevel(Uri uri) {
        if (uri == null || !"https".equalsIgnoreCase(uri.getScheme()) || uri.getUserInfo() != null ||
                (uri.getPort() != -1 && uri.getPort() != 443)) return false;
        String host = uri.getHost();
        return host != null && (host.equalsIgnoreCase("web.telegram.org") || host.equalsIgnoreCase("web.max.ru"));
    }

    @SuppressLint("SetJavaScriptEnabled")
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 28 && !dataDirectorySuffixConfigured) {
            try {
                WebView.setDataDirectorySuffix("portal_messenger");
                dataDirectorySuffixConfigured = true;
            } catch (IllegalStateException unavailable) { finish(); return; }
        }
        if (ACTION_CLEAR_SESSION.equals(getIntent().getAction())) {
            if (Build.VERSION.SDK_INT < 28) { finish(); return; }
            clearingSession = true;
            pendingProvider = null;
            clearProviderData(() -> {
                clearingSession = false;
                if (pendingProvider != null) {
                    provider = pendingProvider;
                    pendingProvider = null;
                    readRelayTicket(pendingRelay);
                    pendingRelay = null;
                    createMessengerUI();
                } else finish();
            });
            return;
        }
        provider = normalizedProvider(getIntent().getStringExtra("provider"));
        readRelayTicket(getIntent().getStringExtra("relay"));
        if (Build.VERSION.SDK_INT < 28) {
            // API 26-27 cannot safely host the isolated WebView process/profile required here.
            // Do not fall back to the OS browser, whose provider session is not PORTAL-user scoped.
            Toast.makeText(this, "Мессенджер требует Android 9 или новее для изоляции сессии", Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        createMessengerUI();
    }

    private void createMessengerUI() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(245, 248, 253));
        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setGravity(Gravity.CENTER);
        tabs.setPadding(12, 12, 12, 8);

        telegram = tab("Telegram", "telegram");
        max = tab("MAX", "max");
        relayButton = new Button(this);
        relayButton.setAllCaps(false);
        relayButton.setVisibility(View.GONE);
        tabs.addView(telegram, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        tabs.addView(max, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        tabs.addView(relayButton, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        root.addView(tabs, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        status = new TextView(this);
        status.setGravity(Gravity.CENTER);
        status.setPadding(16, 8, 16, 8);
        status.setTextColor(Color.DKGRAY);
        root.addView(status, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        browser = new WebView(this);
        WebSettings settings = browser.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        if (Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(true);
        settings.setSupportMultipleWindows(false);
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(browser, true);

        browser.setWebViewClient(new WebViewClient() {
            private boolean handleMainFrame(Uri uri) {
                if (isAllowedTopLevel(uri)) return false;
                showStatus("Переход заблокирован: разрешены только официальные Telegram и MAX");
                return true;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) return false;
                return handleMainFrame(request.getUrl());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) { return handleMainFrame(Uri.parse(url)); }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                showStatus(relayActive ? "Загрузка через PORTAL Relay…" : "Прямое подключение…");
            }
            @Override public void onPageFinished(WebView view, String url) {
                showStatus(relayActive ? "PORTAL Relay активен" : "Прямое подключение");
            }
            @Override public void onReceivedHttpAuthRequest(WebView view, HttpAuthHandler handler, String host, String realm) {
                if (relayActive && relayConfigured() && host != null && host.equalsIgnoreCase(relayHost) &&
                        (realm == null || relayRealm.equals(realm))) {
                    handler.proceed(relayUser, relayPassword);
                } else handler.cancel();
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                int code = error == null ? 0 : error.getErrorCode();
                if (request.isForMainFrame()) showLoadFailure(code);
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) showLoadFailure(response.getStatusCode());
            }
        });
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onCreateWindow(WebView view, boolean dialog, boolean userGesture, android.os.Message resultMsg) { return false; }
        });
        root.addView(browser, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        updateTabs();
        select(provider);
    }

    private void clearProviderData(Runnable complete) {
        CookieManager cookies = CookieManager.getInstance();
        cookies.removeAllCookies(removed -> {
            WebStorage.getInstance().deleteAllData();
            cookies.flush();
            runOnUiThread(complete);
        });
    }

    private Button tab(String label, String key) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(v -> select(key));
        return button;
    }

    private static String normalizedProvider(String value) { return "max".equalsIgnoreCase(value) ? "max" : "telegram"; }

    private void readRelayTicket(String raw) {
        clearRelayTicket();
        relayRequired = true;
        if (raw == null || raw.isBlank()) return;
        try {
            JSONObject data = new JSONObject(raw);
            if (!"telegram".equals(data.optString("provider", "")) || !data.has("required") || data.isNull("required") ||
                    !data.has("enabled") || data.isNull("enabled")) return;
            boolean required = data.getBoolean("required");
            boolean enabled = data.getBoolean("enabled");
            if (!enabled) { relayRequired = required; clearRelayTicket(); return; }
            String proxy = data.optString("proxy_url", "");
            URI uri = URI.create(proxy);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null ||
                    (uri.getPort() != -1 && (uri.getPort() < 1 || uri.getPort() > 65535)) ||
                    (uri.getPath() != null && !uri.getPath().isEmpty() && !"/".equals(uri.getPath()))) return;
            relayProxyUrl = proxy.endsWith("/") ? proxy.substring(0, proxy.length() - 1) : proxy;
            relayHost = uri.getHost();
            relayUser = data.optString("username", "");
            relayPassword = data.optString("password", "");
            relayRealm = data.optString("realm", "PORTAL Messenger Relay");
            long expiry = Instant.parse(data.getString("expires_at")).getEpochSecond();
            if (expiry <= System.currentTimeMillis() / 1000L || relayUser.length() < 1 || relayUser.length() > 256 || relayPassword.length() < 1 || relayPassword.length() > 256 || relayRealm.length() > 128) {
                clearRelayTicket(); relayRequired = true;
            } else relayRequired = required;
        } catch (Exception ignored) { clearRelayTicket(); }
    }

    private void clearRelayTicket() {
        relayProxyUrl = relayHost = relayUser = relayPassword = "";
        relayRealm = "PORTAL Messenger Relay";
    }

    private boolean relayConfigured() {
        return !relayProxyUrl.isEmpty() && !relayHost.isEmpty() && !relayUser.isEmpty() && !relayPassword.isEmpty() &&
                WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE);
    }

    private void updateTabs() {
        telegram.setEnabled(!"telegram".equals(provider));
        max.setEnabled(!"max".equals(provider));
        if (relayButton != null) {
            relayButton.setVisibility(View.GONE);
        }
    }

    private void showStatus(String message) {
        if (status == null) return;
        status.setText(message);
        status.setVisibility(message == null || message.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void showLoadFailure(int code) {
        String suffix = code == WebViewClient.ERROR_PROXY_AUTHENTICATION ? " Ошибка авторизации Relay." : "";
        showStatus("Официальный клиент не загрузился." + suffix + " Проверьте сеть и повторите.");
    }

    private String targetUrl() { return "max".equals(provider) ? MAX_URL : TELEGRAM_URL; }
    private void loadCurrent() { if (browser != null) browser.loadUrl(targetUrl()); }

    private void select(String key) {
        provider = normalizedProvider(key);
        updateTabs();
        if ("max".equals(provider)) { relayActive = false; useDirectChannel(); return; }
        if (relayRequired) {
            if (Build.VERSION.SDK_INT < 28 || !relayConfigured()) { showStatus("Telegram доступен только через защищённый канал PORTAL; канал пока недоступен."); return; }
            useRelayChannel(false);
            return;
        }
        if (relayConfigured()) { useRelayChannel(false); return; }
        useDirectChannel();
    }

    private void useDirectChannel() {
        relayActive = false;
        updateTabs();
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.PROXY_OVERRIDE)) {
            loadCurrent();
            return;
        }
        ProxyController.getInstance().clearProxyOverride(ContextCompat.getMainExecutor(this), () -> {
            showStatus("Прямое подключение…");
            loadCurrent();
        });
    }

    private void useRelayChannel(boolean automatic) {
        if (!"telegram".equals(provider)) { useDirectChannel(); return; }
        if (!relayConfigured()) {
            if (relayRequired) showStatus("Telegram доступен только через защищённый канал PORTAL; канал пока недоступен.");
            else showStatus("PORTAL Relay ещё не настроен сервером");
            return;
        }
        relayActive = true;
        updateTabs();
        ProxyConfig config = new ProxyConfig.Builder().addProxyRule(relayProxyUrl).build();
        ProxyController.getInstance().setProxyOverride(config, ContextCompat.getMainExecutor(this), () -> {
            showStatus("PORTAL Relay…");
            loadCurrent();
        });
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (ACTION_CLEAR_SESSION.equals(intent.getAction())) {
            pendingProvider = null;
            clearRelayTicket();
            clearingSession = true;
            if (browser != null) { browser.stopLoading(); browser.clearCache(true); browser.clearFormData(); browser.clearHistory(); browser.destroy(); browser = null; }
            clearProviderData(() -> {
                clearingSession = false;
                if (pendingProvider != null) {
                    provider = pendingProvider;
                    pendingProvider = null;
                    readRelayTicket(pendingRelay);
                    pendingRelay = null;
                    createMessengerUI();
                } else finish();
            });
            return;
        }
        String requestedProvider = normalizedProvider(intent.getStringExtra("provider"));
        if (clearingSession) {
            pendingProvider = requestedProvider;
            pendingRelay = intent.getStringExtra("relay");
            return;
        }
        if (browser != null) {
            readRelayTicket(intent.getStringExtra("relay"));
            updateTabs();
            select(requestedProvider);
        }
        else {
            provider = requestedProvider;
            readRelayTicket(intent.getStringExtra("relay"));
            createMessengerUI();
        }
    }

    @Override public void onBackPressed() {
        if (browser != null && browser.canGoBack()) browser.goBack(); else super.onBackPressed();
    }

    @Override protected void onPause() {
        if (browser != null) CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override protected void onDestroy() {
        clearRelayTicket();
        if (browser != null) { browser.stopLoading(); browser.destroy(); browser = null; }
        super.onDestroy();
    }
}
