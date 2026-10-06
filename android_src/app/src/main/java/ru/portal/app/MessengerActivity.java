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
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;

/**
 * Device-local Messenger container. It deliberately has no PORTAL JavaScript bridge:
 * provider cookies/session data stay inside the dedicated WebView process/profile.
 */
public final class MessengerActivity extends Activity {
    static final String TELEGRAM_URL = "https://web.telegram.org/a/";
    static final String MAX_URL = "https://web.max.ru/";
    private WebView browser;
    private Button telegram;
    private Button max;
    private String provider = "telegram";

    public static boolean isAllowedTopLevel(Uri uri) {
        if (uri == null || !"https".equalsIgnoreCase(uri.getScheme()) || uri.getUserInfo() != null ||
                (uri.getPort() != -1 && uri.getPort() != 443)) return false;
        String host = uri.getHost();
        return host != null && (host.equalsIgnoreCase("web.telegram.org") || host.equalsIgnoreCase("web.max.ru"));
    }

    @SuppressLint("SetJavaScriptEnabled")
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 28) {
            try { WebView.setDataDirectorySuffix("portal_messenger"); } catch (IllegalStateException ignored) { }
        }
        provider = normalizedProvider(getIntent().getStringExtra("provider"));
        if (Build.VERSION.SDK_INT < 28) {
            // Android 8 cannot safely use a second persistent WebView data directory while PORTAL is open.
            // Fail safe to the same official provider URL in the system browser instead of sharing PORTAL WebView storage.
            Uri official = Uri.parse("max".equals(provider) ? MAX_URL : TELEGRAM_URL);
            try { startActivity(new Intent(Intent.ACTION_VIEW, official)); } catch (Exception ignored) { }
            finish();
            return;
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(245, 248, 253));
        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);
        tabs.setGravity(Gravity.CENTER);
        tabs.setPadding(12, 12, 12, 8);

        telegram = tab("Telegram", "telegram");
        max = tab("MAX", "max");
        tabs.addView(telegram, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        tabs.addView(max, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        root.addView(tabs, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

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
            private boolean handle(Uri uri) {
                if (isAllowedTopLevel(uri)) return false;
                return true; // fail closed: arbitrary top-level navigation never leaves this profile.
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return handle(request.getUrl()); }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) { return handle(Uri.parse(url)); }
        });
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onCreateWindow(WebView view, boolean dialog, boolean userGesture, android.os.Message resultMsg) { return false; }
        });
        root.addView(browser, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
        select(provider);
    }

    private Button tab(String label, String key) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(v -> select(key));
        return button;
    }

    private static String normalizedProvider(String value) { return "max".equalsIgnoreCase(value) ? "max" : "telegram"; }
    private void select(String key) {
        provider = normalizedProvider(key);
        telegram.setEnabled(!"telegram".equals(provider));
        max.setEnabled(!"max".equals(provider));
        String target = "max".equals(provider) ? MAX_URL : TELEGRAM_URL;
        Uri current = browser.getUrl() == null ? null : Uri.parse(browser.getUrl());
        if (current == null || !target.equalsIgnoreCase(current.toString())) browser.loadUrl(target);
    }

    @Override public void onBackPressed() {
        if (browser != null && browser.canGoBack()) browser.goBack(); else super.onBackPressed();
    }

    @Override protected void onPause() {
        if (browser != null) CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override protected void onDestroy() {
        if (browser != null) { browser.stopLoading(); browser.destroy(); browser = null; }
        super.onDestroy();
    }
}
