package ru.portal.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.Manifest;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.ValueCallback;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.view.View;
import androidx.core.content.FileProvider;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Locale;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.UUID;
import org.json.JSONArray;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 42032;
    private WebView webView;
    private PortalBridge bridge;
    private ValueCallback<Uri[]> filePathCallback;
    private static final int NOTIFICATION_PERMISSION_REQUEST = 6201;

    @SuppressLint({"SetJavaScriptEnabled", "JavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        applyImmersiveMode();
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
                Uri uri=request.getUrl();
                if (uri.toString().startsWith("file:///android_asset/")) return false;
                openOfficialSource(uri);
                return true;
            }
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Uri uri=Uri.parse(url);
                if (uri.toString().startsWith("file:///android_asset/")) return false;
                openOfficialSource(uri);
                return true;
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                filePathCallback = callback;
                try {
                    Intent intent = params.createIntent();
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (Exception ignored) {
                    if (filePathCallback != null) filePathCallback.onReceiveValue(null);
                    filePathCallback = null;
                    return true;
                }
            }
        });
        bridge = new PortalBridge(this, webView);
        webView.addJavascriptInterface(bridge, "PortalNative");
        webView.loadUrl("file:///android_asset/index.html");
    }

    private void openOfficialSource(Uri uri) {
        String host=uri.getHost();
        if (!"https".equalsIgnoreCase(uri.getScheme()) || host==null ||
                !(host.equalsIgnoreCase("seller.ozon.ru") || host.equalsIgnoreCase("seller.wildberries.ru")) ||
                uri.getUserInfo()!=null || (uri.getPort()!=-1 && uri.getPort()!=443)) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (Exception ignored) { }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST && filePathCallback != null) {
            Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            filePathCallback.onReceiveValue(result);
            filePathCallback = null;
            applyImmersiveMode();
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    private void applyImmersiveMode() {
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        );
    }

    @Override protected void onResume() {
        super.onResume();
        if (webView != null) webView.postDelayed(() -> webView.evaluateJavascript("window.portalForegroundRefresh&&window.portalForegroundRefresh()", null), 250);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) applyImmersiveMode();
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
        private final PortalLocalCache localCache;
        private final ExecutorService executor = Executors.newFixedThreadPool(3);
        private volatile boolean closed;
        private volatile String cacheCompany = "";
        private volatile String healthyServerBase = "";
        private volatile long healthyServerUntilMs;
        private static final long CACHE_MAX_AGE_MS = 30L * 24 * 60 * 60 * 1000;
        private static final long SERVER_HEALTH_TTL_MS = 2L * 60 * 1000;
        private static final String DEFAULT_URL = BuildConfig.DEFAULT_API_URL;
        private static final String SERVER_DISCOVERY_URL = BuildConfig.SERVER_DISCOVERY_URL;
        private static final String PRIMARY_API_URL = "https://api.vart-portal.ru";
        private static final String TRUSTED_FALLBACK_API_URL = "https://reserve-api.vart-portal.ru";
        private static final String LEGACY_API_URL = "https://2a03-6f00-a--1-f426.sslip.io";

        PortalBridge(Context context, WebView webView) {
            this.context = context;
            this.webView = webView;
            this.localCache = new PortalLocalCache(context);
            prefs = context.getSharedPreferences("portal_settings", Context.MODE_PRIVATE);
            migrateAutomaticServerAfterUpgrade();
        }

        private void migrateAutomaticServerAfterUpgrade() {
            if (!"release".equals(BuildConfig.RELEASE_CHANNEL)) return;
            int currentVersion = BuildConfig.VERSION_CODE;
            if (prefs.getInt("server_config_version_code", 0) == currentVersion) return;

            String saved = prefs.getString("server_url", "");
            String previous = saved == null ? "" : saved.trim();
            String target = DEFAULT_URL == null ? "" : DEFAULT_URL.trim();
            while (target.endsWith("/")) target = target.substring(0, target.length() - 1);

            boolean managed = previous.isEmpty() || isAutomaticPortalServer(previous) || isLegacyLocalServer(previous);
            if (managed && target.startsWith("https://")) {
                if (isAutomaticPortalServer(previous) && !previous.equalsIgnoreCase(target)
                        && !localCache.migrateOutboxOrigin(previous, target)) {
                    return;
                }
                prefs.edit().putString("server_url", target)
                        .putInt("server_config_version_code", currentVersion).apply();
                healthyServerBase = "";
                healthyServerUntilMs = 0;
                return;
            }

            prefs.edit().putInt("server_config_version_code", currentVersion).apply();
        }

        @JavascriptInterface
        public String getBuild() {
            return "PORTAL Android · Build " + BuildConfig.VERSION_NAME;
        }

        @JavascriptInterface
        public boolean openMessengerWindow(String provider) {
            String selected = "max".equalsIgnoreCase(provider) ? "max" : "telegram";
            try {
                Intent intent = new Intent(context, MessengerActivity.class).putExtra("provider", selected);
                intent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                context.startActivity(intent);
                return true;
            } catch (Exception ignored) { return false; }
        }

        @JavascriptInterface
        public void scheduleOrganizerReminders(String json) {
            if (!(context instanceof Activity)) return;
            Activity activity = (Activity) context;
            try {
                JSONArray reminders = new JSONArray(json == null ? "[]" : json);
                if (reminders.length() > 50) return;
                if (reminders.length() > 0 && Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                    activity.runOnUiThread(() -> activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_PERMISSION_REQUEST));
                    return;
                }
                NotificationManager notifications = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
                if (notifications == null) return;
                if (Build.VERSION.SDK_INT >= 26) notifications.createNotificationChannel(new NotificationChannel("organizer_reminders", "Напоминания Органайзера", NotificationManager.IMPORTANCE_DEFAULT));
                AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
                if (alarms == null) return;
                SharedPreferences reminderPrefs = context.getSharedPreferences("organizer_reminders", Context.MODE_PRIVATE);
                java.util.Set<String> previous = reminderPrefs.getStringSet("ids", java.util.Collections.emptySet());
                java.util.Set<String> current = new java.util.HashSet<>();
                for (int i = 0; i < reminders.length(); i++) {
                    JSONObject reminder = reminders.optJSONObject(i);
                    if (reminder == null) continue;
                    String id = reminder.optString("id", "");
                    String title = reminder.optString("title", "Задача");
                    long at;
                    try {
                        String value = reminder.optString("at", "");
                        try { at = java.time.Instant.parse(value).toEpochMilli(); }
                        catch (Exception noZone) { at = java.time.LocalDateTime.parse(value).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli(); }
                    } catch (Exception ignored) { continue; }
                    if (!id.matches("[A-Za-z0-9_-]{1,80}") || at <= System.currentTimeMillis()) continue;
                    current.add(id);
                    int requestId = id.hashCode();
                    Intent intent = new Intent(context, OrganizerReminderReceiver.class).putExtra("id", id).putExtra("title", title);
                    PendingIntent pending = PendingIntent.getBroadcast(context, requestId, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                    if (Build.VERSION.SDK_INT >= 23) alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending); else alarms.set(AlarmManager.RTC_WAKEUP, at, pending);
                }
                for (String id : previous) if (!current.contains(id)) {
                    Intent intent = new Intent(context, OrganizerReminderReceiver.class);
                    PendingIntent pending = PendingIntent.getBroadcast(context, id.hashCode(), intent, PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
                    if (pending != null) { alarms.cancel(pending); pending.cancel(); }
                }
                reminderPrefs.edit().putStringSet("ids", current).apply();
            } catch (Exception ignored) { }
        }

        @JavascriptInterface
        public String getAppMetadata() {
            try {
                return new JSONObject().put("applicationId", BuildConfig.APPLICATION_ID)
                    .put("versionName", BuildConfig.VERSION_NAME).put("versionCode", BuildConfig.VERSION_CODE)
                    .put("buildNumber", BuildConfig.BUILD_NUMBER).put("buildDate", BuildConfig.BUILD_DATE)
                    .put("channel", BuildConfig.RELEASE_CHANNEL)
                    .put("updatesConfigured", !BuildConfig.UPDATE_MANIFEST_URL.isEmpty())
                    .put("platform", "Android").toString();
            } catch (Exception ignored) { return "{}"; }
        }

        private void deliver(String id, String result) {
            ((Activity) context).runOnUiThread(() -> {
                if (!closed) webView.evaluateJavascript("window.PortalBridgeResult(" + JSONObject.quote(id) + "," + JSONObject.quote(result) + ")", null);
            });
        }

        @JavascriptInterface
        public void requestAsync(String id, String method, String path, String body, String token, String company) {
            String verb = method == null ? "GET" : method.toUpperCase(Locale.ROOT);
            String localCompany = cacheCompany;
            executor.execute(() -> {
                // Resolve a healthy PORTAL endpoint before any authenticated request is sent.
                String base = resolveServerForRequest(getServerUrl());
                boolean cacheable = cacheableGet(verb, path, token, localCompany);
                if (cacheable) {
                    String cached = localCache.read(base, localCompany, path);
                    String ready = cachedResponse(cached);
                    if (ready != null) {
                        deliver(id, ready);
                        String fresh = requestAt(base, verb, path, body, token, company);
                        if (responseOk(fresh)) localCache.write(base, localCompany, path, fresh);
                        return;
                    }
                }
                String result = requestAt(base, verb, path, body, token, company);
                if (cacheable && responseOk(result)) localCache.write(base, localCompany, path, result);
                if ("POST".equals(verb) && responseOk(result) && !localCompany.isEmpty())
                    invalidateCacheForMutation(base, localCompany, path);
                deliver(id, result);
            });
        }

        private boolean isAutomaticPortalServer(String value) {
            if (value == null) return false;
            String base = value.trim();
            while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
            return PRIMARY_API_URL.equalsIgnoreCase(base) || TRUSTED_FALLBACK_API_URL.equalsIgnoreCase(base)
                    || LEGACY_API_URL.equalsIgnoreCase(base);
        }

        private void markHealthyServer(String base) {
            healthyServerBase = base;
            healthyServerUntilMs = System.currentTimeMillis() + SERVER_HEALTH_TTL_MS;
        }

        private synchronized String activateTrustedFallback(String previous) {
            if (!isAutomaticPortalServer(previous) || TRUSTED_FALLBACK_API_URL.equalsIgnoreCase(previous)) return previous;
            if (!probeOfficialServer(TRUSTED_FALLBACK_API_URL)) return previous;
            if (!localCache.migrateOutboxOrigin(previous, TRUSTED_FALLBACK_API_URL)) return previous;
            prefs.edit().putString("server_url", TRUSTED_FALLBACK_API_URL).apply();
            markHealthyServer(TRUSTED_FALLBACK_API_URL);
            return TRUSTED_FALLBACK_API_URL;
        }

        private synchronized String resolveServerForRequest(String requestedBase) {
            String base = requestedBase == null ? "" : requestedBase.trim();
            if (!isAutomaticPortalServer(base)) return base;
            long now = System.currentTimeMillis();
            if (base.equalsIgnoreCase(healthyServerBase) && now < healthyServerUntilMs) return base;
            if (probeOfficialServer(base)) {
                markHealthyServer(base);
                return base;
            }
            return activateTrustedFallback(base);
        }

        @JavascriptInterface
        public boolean setCacheCompany(String value) {
            String next = value == null ? "" : value.trim();
            cacheCompany = next.matches("[1-9][0-9]{0,9}") ? next : "";
            return !cacheCompany.isEmpty();
        }

        @JavascriptInterface
        public boolean clearCompanyCache() {
            String company = cacheCompany;
            return company.isEmpty() || localCache.clearCompany(getServerUrl(), company);
        }

        private boolean cacheableGet(String method, String path, String token, String company) {
            if (!"GET".equals(method) || token == null || token.isEmpty() || company == null || company.isEmpty() || path == null) return false;
            return path.matches("/api/company")
                    || path.matches("/api/(?:admin/)?clients(?:\\?.*)?")
                    || path.matches("/api/clients/[0-9]+(?:/operations)?(?:\\?.*)?")
                    || path.matches("/api/admin/clients/[0-9]+/operations(?:\\?.*)?")
                    || path.matches("/api/(?:users|materials|jobs)(?:\\?.*)?")
                    || path.matches("/api/v3/(?:catalog|products|client-requisites|client-name-history|tariff-history|today|tasks|timers|batches|invoices|receivables|finance|analytics|payroll-periods|documents|settings|permissions|chat-users)(?:\\?.*)?");
        }

        private void invalidateCacheForMutation(String base, String company, String path) {
            if (path == null || company == null || company.isEmpty()) return;
            String[] keys;
            if (path.matches("/api/v3/work(?:\\?.*)?")) {
                keys = new String[]{"/api/v3/today","/api/v3/tasks","/api/v3/timers","/api/v3/finance","/api/v3/analytics","/api/v3/invoices","/api/v3/receivables"};
            } else if (path.matches("/api/v3/links(?:\\?.*)?")) {
                keys = new String[]{"/api/v3/today","/api/v3/tasks","/api/v3/batches","/api/v3/finance","/api/v3/analytics","/api/v3/invoices","/api/v3/receivables"};
            } else if (path.matches("/api/v3/(?:batches|tasks)(?:\\?.*)?")) {
                keys = new String[]{"/api/v3/today","/api/v3/tasks","/api/v3/timers","/api/v3/batches","/api/v3/finance","/api/v3/analytics"};
            } else if (path.matches("/api/v3/(?:shipments|returns)(?:\\?.*)?")) {
                keys = new String[]{"/api/v3/today","/api/v3/tasks","/api/v3/batches","/api/v3/finance","/api/v3/analytics","/api/v3/invoices","/api/v3/receivables"};
            } else if (path.matches(".*/(?:tariffs?|operations?|products?)(?:/|\\?|$).*")) {
                keys = new String[]{"/api/v3/catalog","/api/v3/tariff-history","/api/v3/products","/api/v3/today","/api/v3/finance","/api/v3/analytics"};
            } else if (path.matches(".*/clients?(?:/|\\?|$).*")) {
                keys = new String[]{"/api/clients","/api/admin/clients","/api/v3/catalog","/api/v3/client-name-history","/api/v3/client-requisites","/api/v3/today","/api/v3/finance","/api/v3/analytics"};
            } else if (path.matches(".*/materials?(?:/|\\?|$).*")) {
                keys = new String[]{"/api/materials","/api/v3/today","/api/v3/finance","/api/v3/analytics"};
            } else if (path.matches(".*/(?:users?|invitations?|company-access|permissions)(?:/|\\?|$).*")) {
                keys = new String[]{"/api/users","/api/v3/permissions","/api/v3/chat-users"};
            } else if (path.matches(".*/(?:invoices?|payments?)(?:/|\\?|$).*")) {
                keys = new String[]{"/api/v3/invoices","/api/v3/receivables","/api/v3/finance","/api/v3/today"};
            } else if (path.matches(".*/settings(?:/|\\?|$).*")) {
                keys = new String[]{"/api/company","/api/v3/settings","/api/v3/today"};
            } else {
                return;
            }
            for (String key : keys) localCache.delete(base, company, key);
        }

        private String cachedResponse(String envelopeJson) {
            if (envelopeJson == null || envelopeJson.isEmpty()) return null;
            try {
                JSONObject envelope = new JSONObject(envelopeJson);
                long savedAt = envelope.optLong("savedAt", 0);
                JSONObject data = envelope.optJSONObject("data");
                if (envelope.optInt("v", 0) != 1 || savedAt <= 0 || data == null ||
                        System.currentTimeMillis() - savedAt > CACHE_MAX_AGE_MS) return null;
                JSONObject copy = new JSONObject(data.toString());
                copy.put("cached", true);
                return copy.toString();
            } catch (Exception ignored) { return null; }
        }

        private boolean responseOk(String json) {
            try { return new JSONObject(json).optBoolean("ok", false); }
            catch (Exception ignored) { return false; }
        }


        private boolean queueableMutationPath(String path) {
            return "/api/v3/work".equals(path) || "/api/v3/links".equals(path) || "/api/v3/batches".equals(path)
                    || "/api/v3/tasks".equals(path) || "/api/v3/shipments".equals(path) || "/api/v3/returns".equals(path);
        }

        @JavascriptInterface
        public boolean queueMutation(String json) {
            try {
                String company = cacheCompany;
                if (company.isEmpty() || json == null || json.length() > 512 * 1024) return false;
                JSONObject row = new JSONObject(json);
                String requestId = row.optString("request_id", "");
                String method = row.optString("method", "");
                String path = row.optString("path", "");
                JSONObject body = row.optJSONObject("body");
                if (!"POST".equals(method) || !queueableMutationPath(path) || body == null ||
                        !requestId.matches("[0-9a-fA-F-]{36}") || !requestId.equals(body.optString("request_id", ""))) return false;
                return localCache.enqueueMutation(getServerUrl(), company, requestId, row.toString());
            } catch (Exception ignored) {
                return false;
            }
        }

        @JavascriptInterface
        public String pendingMutations() {
            String company = cacheCompany;
            return company.isEmpty() ? "[]" : localCache.pendingMutations(getServerUrl(), company);
        }

        @JavascriptInterface
        public boolean removeMutation(String requestId) {
            String company = cacheCompany;
            return !company.isEmpty() && localCache.removeMutation(getServerUrl(), company, requestId);
        }

        @JavascriptInterface
        public int pendingMutationCount() {
            String company = cacheCompany;
            return company.isEmpty() ? 0 : localCache.pendingMutationCount(getServerUrl(), company);
        }

        @JavascriptInterface
        public void checkUpdates(String id) {
            executor.execute(() -> deliver(id, checkUpdatesAndServer()));
        }

        @JavascriptInterface
        public void downloadAndInstallUpdate(String id, String manifestJson) {
            executor.execute(() -> downloadUpdate(id, manifestJson));
        }

        @JavascriptInterface
        public void saveBase64FileAsync(String id, String filename, String mimeType, String encoded) {
            executor.execute(() -> deliver(id, saveBase64File(filename, mimeType, encoded)));
        }

        @JavascriptInterface
        public void shareBase64FileAsync(String id, String filename, String mimeType, String encoded,
                                         String recipient, String subject, String message) {
            executor.execute(() -> {
                String result = prepareShare(filename, mimeType, encoded);
                try {
                    JSONObject parsed = new JSONObject(result);
                    if (!parsed.optBoolean("ok")) { deliver(id, result); return; }
                    Uri uri = Uri.parse(parsed.getString("uri"));
                    ((Activity) context).runOnUiThread(() -> {
                        try {
                            Intent send = new Intent(Intent.ACTION_SEND);
                            send.setType(mimeType);
                            send.putExtra(Intent.EXTRA_STREAM, uri);
                            String cleanRecipient = recipient == null ? "" : recipient.trim();
                            if (cleanRecipient.length() <= 254 && cleanRecipient.matches("[^\\s@,;]+@[^\\s@,;]+\\.[^\\s@,;]+"))
                                send.putExtra(Intent.EXTRA_EMAIL, new String[]{cleanRecipient});
                            if (subject != null && !subject.trim().isEmpty()) send.putExtra(Intent.EXTRA_SUBJECT, subject.trim().substring(0, Math.min(160, subject.trim().length())));
                            if (message != null && !message.trim().isEmpty()) send.putExtra(Intent.EXTRA_TEXT, message.trim().substring(0, Math.min(2000, message.trim().length())));
                            send.setClipData(ClipData.newUri(context.getContentResolver(), "PORTAL document", uri));
                            send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                            context.startActivity(Intent.createChooser(send, "Поделиться документом"));
                            deliver(id, "{\"ok\":true}");
                        } catch (Exception ignored) { deliver(id, "{\"ok\":false,\"error\":\"Не удалось открыть меню отправки.\"}"); }
                    });
                } catch (Exception ignored) { deliver(id, "{\"ok\":false,\"error\":\"Не удалось подготовить документ.\"}"); }
            });
        }

        private String prepareShare(String filename, String mimeType, String encoded) {
            try {
                String expected = filename == null ? "" : filename.toLowerCase(java.util.Locale.ROOT);
                boolean allowed = ("application/pdf".equals(mimeType) && expected.endsWith(".pdf"))
                    || ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet".equals(mimeType) && expected.endsWith(".xlsx"))
                    || ("application/json".equals(mimeType) && expected.endsWith(".json"));
                if (!allowed || !filename.matches("[A-Za-z0-9._-]{1,120}") || encoded == null || encoded.length() > 28 * 1024 * 1024) throw new Exception();
                byte[] data = Base64.decode(encoded, Base64.DEFAULT);
                if (data.length == 0 || data.length > 20 * 1024 * 1024) throw new Exception();
                File dir = new File(context.getCacheDir(), "shared");
                if (!dir.exists() && !dir.mkdirs()) throw new Exception();
                long now = System.currentTimeMillis(), total = 0;
                File[] cached = dir.listFiles();
                if (cached != null) for (File old : cached) {
                    if (now - old.lastModified() > 24L * 60 * 60 * 1000) old.delete();
                    else total += old.length();
                }
                if (total + data.length > 40L * 1024 * 1024) throw new Exception();
                File file = new File(dir, UUID.randomUUID().toString() + "_" + filename);
                try (FileOutputStream out = new FileOutputStream(file)) { out.write(data); }
                Uri uri = FileProvider.getUriForFile(context, BuildConfig.APPLICATION_ID + ".files", file);
                return new JSONObject().put("ok", true).put("uri", uri.toString()).toString();
            } catch (Exception ignored) { return "{\"ok\":false,\"error\":\"Не удалось подготовить документ.\"}"; }
        }

        private String saveBase64File(String filename, String mimeType, String encoded) {
            Uri pending = null;
            try {
                if (filename == null || !filename.matches("[A-Za-z0-9._-]{1,120}") || encoded == null
                        || encoded.length() > 28 * 1024 * 1024) throw new Exception();
                boolean allowedType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet".equals(mimeType)
                        || "application/pdf".equals(mimeType)
                        || "application/json".equals(mimeType)
                        || "image/jpeg".equals(mimeType) || "image/png".equals(mimeType)
                        || "image/webp".equals(mimeType) || "text/plain".equals(mimeType);
                if (!allowedType) throw new Exception();
                byte[] data = Base64.decode(encoded, Base64.DEFAULT);
                if (data.length == 0 || data.length > 20 * 1024 * 1024) throw new Exception();
                String location;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.Downloads.DISPLAY_NAME, filename);
                    values.put(MediaStore.Downloads.MIME_TYPE, mimeType);
                    values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/PORTAL");
                    values.put(MediaStore.Downloads.IS_PENDING, 1);
                    pending = context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (pending == null) throw new Exception();
                    try (OutputStream out = context.getContentResolver().openOutputStream(pending, "w")) {
                        if (out == null) throw new Exception();
                        out.write(data);
                    }
                    values.clear(); values.put(MediaStore.Downloads.IS_PENDING, 0);
                    context.getContentResolver().update(pending, values, null, null);
                    pending = null;
                    location = "Downloads/PORTAL/" + filename;
                } else {
                    File base = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                    if (base == null) base = context.getFilesDir();
                    File dir = new File(base, "PORTAL");
                    if (!dir.exists() && !dir.mkdirs()) throw new Exception();
                    File file = new File(dir, filename);
                    try (FileOutputStream out = new FileOutputStream(file)) { out.write(data); }
                    location = file.getAbsolutePath();
                }
                return new JSONObject().put("ok", true).put("location", location).toString();
            } catch (Exception ignored) {
                if (pending != null) try { context.getContentResolver().delete(pending, null, null); } catch (Exception ignoredDelete) { }
                return "{\"ok\":false,\"error\":\"Не удалось сохранить документ.\"}";
            }
        }

        private String checkUpdatesAndServer() {
            JSONObject server = refreshOfficialServer();
            String updateRaw = fetchUpdateManifest();
            try {
                JSONObject update = new JSONObject(updateRaw);
                update.put("serverChecked", server.optBoolean("checked", false));
                update.put("serverChanged", server.optBoolean("changed", false));
                update.put("serverUrl", server.optString("serverUrl", getServerUrl()));
                if (server.has("error")) update.put("serverCheckError", server.optString("error", ""));
                return update.toString();
            } catch (Exception ignored) {
                return updateRaw;
            }
        }

        private JSONObject refreshOfficialServer() {
            JSONObject result = new JSONObject();
            try {
                result.put("checked", false).put("changed", false).put("serverUrl", getServerUrl());
                if (!"release".equals(BuildConfig.RELEASE_CHANNEL) || SERVER_DISCOVERY_URL == null || SERVER_DISCOVERY_URL.isEmpty()) return result;
                if (!validDiscoveryUrl(SERVER_DISCOVERY_URL)) throw new Exception("invalid_discovery_url");

                URL source = new URL(SERVER_DISCOVERY_URL);
                HttpURLConnection conn = (HttpURLConnection) source.openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(15000);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Accept", "application/json");
                int code = conn.getResponseCode();
                if (code != 200) { conn.disconnect(); throw new Exception("discovery_http_" + code); }
                long declared = conn.getContentLengthLong();
                if (declared > 16384) { conn.disconnect(); throw new Exception("discovery_too_large"); }
                byte[] payload;
                try (InputStream in = conn.getInputStream(); java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream()) {
                    byte[] buf = new byte[4096]; int n;
                    while ((n = in.read(buf)) != -1) {
                        if (out.size() + n > 16384) throw new Exception("discovery_too_large");
                        out.write(buf, 0, n);
                    }
                    payload = out.toByteArray();
                } finally { conn.disconnect(); }

                JSONObject document = new JSONObject(new String(payload, StandardCharsets.UTF_8));
                if (document.optInt("schemaVersion", 0) != 1) throw new Exception("discovery_schema");
                long revision = document.optLong("revision", 0);
                if (revision < 1) throw new Exception("discovery_revision");
                long storedRevision = prefs.getLong("server_discovery_revision", 0);
                if (storedRevision > revision) throw new Exception("discovery_rollback");
                String updatedAt = document.optString("updatedAt", "");
                try { java.time.Instant.parse(updatedAt); } catch (Exception badDate) { throw new Exception("discovery_date"); }
                String next = normalizeOfficialApiUrl(document.optString("apiUrl", ""));
                if (next == null) throw new Exception("discovery_api_url");
                if (!probeOfficialServer(next)) {
                    String previous = getServerUrl();
                    if (TRUSTED_FALLBACK_API_URL.equalsIgnoreCase(previous)) {
                        if (!probeOfficialServer(previous)) throw new Exception("discovery_server_unreachable");
                        markHealthyServer(previous);
                        result.put("checked", false).put("changed", false).put("serverUrl", previous).remove("error");
                        return result;
                    }
                    String fallback = activateTrustedFallback(previous);
                    if (TRUSTED_FALLBACK_API_URL.equalsIgnoreCase(fallback)) {
                        boolean changed = !fallback.equalsIgnoreCase(previous);
                        result.put("checked", false).put("changed", changed).put("serverUrl", fallback).remove("error");
                        return result;
                    }
                    throw new Exception("discovery_server_unreachable");
                }

                String previous = getServerUrl();
                boolean changed = !next.equalsIgnoreCase(previous);
                if (changed && !localCache.migrateOutboxOrigin(previous, next)) throw new Exception("outbox_migration_failed");
                prefs.edit().putString("server_url", next).putLong("server_discovery_revision", revision).apply();
                markHealthyServer(next);
                result.put("checked", true).put("changed", changed).put("serverUrl", next).remove("error");
                return result;
            } catch (Exception e) {
                try { result.put("error", e.getMessage() == null ? "server_discovery_failed" : e.getMessage()); } catch (Exception ignored) { }
                return result;
            }
        }

        private boolean validDiscoveryUrl(String value) {
            try {
                URL u = new URL(value);
                return "https".equalsIgnoreCase(u.getProtocol()) && u.getUserInfo() == null
                    && "raw.githubusercontent.com".equalsIgnoreCase(u.getHost()) && (u.getPort() == -1 || u.getPort() == 443)
                    && "/portal26ernest-arch/-Portal-zrp/main/portal-server.json".equals(u.getPath())
                    && u.getQuery() == null && u.getRef() == null;
            } catch (Exception e) { return false; }
        }

        private String normalizeOfficialApiUrl(String value) {
            try {
                String trimmed = value == null ? "" : value.trim();
                while (trimmed.endsWith("/")) trimmed = trimmed.substring(0, trimmed.length() - 1);
                URL u = new URL(trimmed);
                String host = u.getHost() == null ? "" : u.getHost().toLowerCase(Locale.ROOT);
                if (!"https".equalsIgnoreCase(u.getProtocol()) || host.isEmpty() || u.getUserInfo() != null
                        || u.getQuery() != null || u.getRef() != null || (u.getPort() != -1 && u.getPort() != 443)
                        || !(u.getPath().isEmpty() || "/".equals(u.getPath()))
                        || !("api.vart-portal.ru".equals(host) || "reserve-api.vart-portal.ru".equals(host))) return null;
                return "https://" + host;
            } catch (Exception e) { return null; }
        }

        private boolean isSafeServerTransport(URL url) {
            if (url == null) return false;
            if ("https".equalsIgnoreCase(url.getProtocol())) return true;
            if (!"http".equalsIgnoreCase(url.getProtocol())) return false;
            String host = url.getHost() == null ? "" : url.getHost().toLowerCase(Locale.ROOT);
            return "localhost".equals(host) || host.endsWith(".localhost")
                    || host.matches("127(?:\\.[0-9]{1,3}){3}") || "::1".equals(host);
        }

        private boolean probeOfficialServer(String base) {
            HttpURLConnection conn = null;
            try {
                URL url = new URL(base + "/api/ping");
                conn = (HttpURLConnection) url.openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(4500);
                conn.setReadTimeout(5000);
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Accept", "application/json");
                if (conn.getResponseCode() != 200) return false;
                String raw = readLimited(conn.getInputStream(), 32768);
                JSONObject ping = new JSONObject(raw);
                String build = ping.optString("build", "");
                return ping.optBoolean("ok", false) && build.startsWith("PORTAL Server");
            } catch (Exception ignored) {
                return false;
            } finally {
                if (conn != null) conn.disconnect();
            }
        }

        private String fetchUpdateManifest() {
            String source = BuildConfig.UPDATE_MANIFEST_URL;
            if (source.isEmpty()) return "{\"ok\":true,\"configured\":false}";
            HttpURLConnection conn = null;
            try {
                if (!validManifestUrl(source)) throw new Exception();
                HttpResult response = getOfficial(source, 65536, true);
                if (response.code != 200) throw new Exception();
                String raw = new String(response.body, StandardCharsets.UTF_8);
                return new JSONObject().put("ok", true).put("configured", true).put("manifest", new JSONObject(raw)).toString();
            } catch (Exception ignored) {
                return "{\"ok\":false,\"error\":\"Сервис обновлений недоступен. Повторите позже.\"}";
            } finally { if (conn != null) conn.disconnect(); }
        }

        private boolean validManifestUrl(String value) {
            try {
                URL u = new URL(value);
                return "https".equalsIgnoreCase(u.getProtocol()) && u.getUserInfo() == null
                    && "github.com".equalsIgnoreCase(u.getHost()) && (u.getPort() == -1 || u.getPort() == 443)
                    && "/portal26ernest-arch/-Portal-zrp/releases/latest/download/portal-update.json".equals(u.getPath())
                    && u.getQuery() == null && u.getRef() == null;
            } catch (Exception e) { return false; }
        }

        private boolean allowedReleaseHost(URL u) {
            String h = u.getHost() == null ? "" : u.getHost().toLowerCase(Locale.ROOT);
            return "github.com".equals(h) || "release-assets.githubusercontent.com".equals(h);
        }

        private HttpResult getOfficial(String address, int limit, boolean json) throws Exception {
            URL url = new URL(address);
            for (int redirects = 0; redirects <= 5; redirects++) {
                if (!"https".equalsIgnoreCase(url.getProtocol()) || url.getUserInfo() != null || !allowedReleaseHost(url)
                        || (url.getPort() != -1 && url.getPort() != 443)) throw new UpdateFailure("invalid_url");
                HttpURLConnection c = (HttpURLConnection) url.openConnection();
                c.setInstanceFollowRedirects(false); c.setConnectTimeout(10000); c.setReadTimeout(20000);
                c.setRequestMethod("GET");
                if (json) c.setRequestProperty("Accept", "application/json");
                int code = c.getResponseCode();
                if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
                    String location = c.getHeaderField("Location"); c.disconnect();
                    if (redirects == 5 || location == null) throw new UpdateFailure("invalid_url");
                    url = new URL(url, location);
                    continue;
                }
                if (code != 200) { c.disconnect(); throw new UpdateFailure("network"); }
                long declared = c.getContentLengthLong();
                if (declared > limit) { c.disconnect(); throw new UpdateFailure("size_limit"); }
                try (InputStream in = c.getInputStream(); java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream()) {
                    byte[] buf = new byte[16384]; int n;
                    while ((n = in.read(buf)) != -1) { if ((long)out.size() + n > limit) throw new UpdateFailure("size_limit"); out.write(buf, 0, n); }
                    return new HttpResult(code, out.toByteArray());
                } finally { c.disconnect(); }
            }
            throw new UpdateFailure("invalid_url");
        }

        private static final class HttpResult { final int code; final byte[] body; HttpResult(int c, byte[] b) { code=c; body=b; } }
        private static final class DownloadResult { final byte[] sha256; final long bytes; DownloadResult(byte[] digest, long size) { sha256=digest; bytes=size; } }
        private static final class UpdateFailure extends Exception { final String kind; UpdateFailure(String k) { kind=k; } }

        private DownloadResult downloadOfficialToFile(String address, File target, long limit) throws Exception {
            URL url = new URL(address);
            for (int redirects = 0; redirects <= 5; redirects++) {
                if (!"https".equalsIgnoreCase(url.getProtocol()) || url.getUserInfo() != null || !allowedReleaseHost(url)
                        || (url.getPort() != -1 && url.getPort() != 443)) throw new UpdateFailure("invalid_url");
                HttpURLConnection c = (HttpURLConnection) url.openConnection();
                c.setInstanceFollowRedirects(false);
                c.setConnectTimeout(10000);
                c.setReadTimeout(30000);
                c.setRequestMethod("GET");
                int code = c.getResponseCode();
                if (code == 301 || code == 302 || code == 303 || code == 307 || code == 308) {
                    String location = c.getHeaderField("Location");
                    c.disconnect();
                    if (redirects == 5 || location == null) throw new UpdateFailure("invalid_url");
                    url = new URL(url, location);
                    continue;
                }
                if (code != 200) { c.disconnect(); throw new UpdateFailure("network"); }
                long declared = c.getContentLengthLong();
                if (declared > limit) { c.disconnect(); throw new UpdateFailure("size_limit"); }
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long total = 0;
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(target)) {
                    byte[] buf = new byte[16384];
                    int n;
                    while ((n = in.read(buf)) != -1) {
                        total += n;
                        if (total > limit) throw new UpdateFailure("size_limit");
                        digest.update(buf, 0, n);
                        out.write(buf, 0, n);
                    }
                    out.getFD().sync();
                    return new DownloadResult(digest.digest(), total);
                } finally {
                    c.disconnect();
                }
            }
            throw new UpdateFailure("invalid_url");
        }

        private void downloadUpdate(String id, String manifestJson) {
            File part = null;
            try {
                JSONObject m = new JSONObject(manifestJson);
                String url = m.getString("apkUrl"), versionName = m.getString("versionName"), hash = m.getString("sha256");
                Object versionValue=m.get("versionCode");
                if (!(versionValue instanceof Number) || ((Number)versionValue).doubleValue()!=((Number)versionValue).longValue()) throw new UpdateFailure("version_mismatch");
                long version = ((Number)versionValue).longValue();
                String publishedAt=m.getString("publishedAt");
                if (m.getInt("schemaVersion") != 1 || !BuildConfig.APPLICATION_ID.equals(m.getString("applicationId"))
                    || !"release".equals(BuildConfig.RELEASE_CHANNEL) || !"release".equals(m.getString("channel"))
                    || version <= BuildConfig.VERSION_CODE || !hash.matches("(?i)[0-9a-f]{64}")
                    || !versionName.matches("[A-Za-z0-9._-]{1,80}")
                    || !m.getString("buildNumber").matches("[A-Za-z0-9._-]{1,40}")
                    || !publishedAt.matches("\\d{4}-\\d{2}-\\d{2}T.*Z") || publishedAt.length() > 40
                    || m.getString("changelog").length() > 4000) throw new UpdateFailure("package_mismatch");
                try { java.time.Instant.parse(publishedAt); } catch (Exception invalidDate) { throw new UpdateFailure("package_mismatch"); }
                String asset = "PORTAL_Android_" + versionName + "_release.apk";
                if (!url.equals("https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-android-v" + versionName + "/" + asset)) throw new UpdateFailure("invalid_url");
                File dir = new File(context.getCacheDir(), "updates");
                if (!dir.exists() && !dir.mkdirs()) throw new UpdateFailure("network");
                cleanUpdateCache(dir);
                part = new File(dir, UUID.randomUUID() + ".part");
                DownloadResult response = downloadOfficialToFile(url, part, 100L * 1024 * 1024);
                byte[] expected = hex(hash);
                if (!MessageDigest.isEqual(expected, response.sha256)) throw new UpdateFailure("checksum_mismatch");
                verifyUpdateApk(part, version, versionName);
                File ready = new File(dir, "portal-update-" + UUID.randomUUID() + ".apk");
                if (!part.renameTo(ready)) throw new UpdateFailure("network");
                part = null;
                final File verified = ready;
                ((Activity)context).runOnUiThread(() -> launchInstaller(id, verified));
            } catch (UpdateFailure e) { if (part != null) part.delete(); deliver(id, updateError(e.kind)); }
            catch (Exception e) { if (part != null) part.delete(); deliver(id, updateError("network")); }
        }

        private byte[] hex(String s) { byte[] b=new byte[32]; for(int i=0;i<b.length;i++) b[i]=(byte)Integer.parseInt(s.substring(i*2,i*2+2),16); return b; }
        private void cleanUpdateCache(File dir) {
            File[] files=dir.listFiles(); if(files==null)return; long now=System.currentTimeMillis(), total=0;
            for(File f:files) { if(now-f.lastModified()>24L*60*60*1000) f.delete(); else total+=f.length(); }
            if(total>200L*1024*1024) for(File f:files) { if(f.isFile()) f.delete(); }
        }
        private void verifyUpdateApk(File apk, long expectedVersion, String expectedName) throws Exception {
            PackageManager pm=context.getPackageManager(); PackageInfo installed, archive;
            if(Build.VERSION.SDK_INT>=28) {
                installed=pm.getPackageInfo(BuildConfig.APPLICATION_ID, PackageManager.GET_SIGNING_CERTIFICATES);
                archive=pm.getPackageArchiveInfo(apk.getAbsolutePath(), PackageManager.GET_SIGNING_CERTIFICATES);
            } else {
                installed=pm.getPackageInfo(BuildConfig.APPLICATION_ID, PackageManager.GET_SIGNATURES);
                archive=pm.getPackageArchiveInfo(apk.getAbsolutePath(), PackageManager.GET_SIGNATURES);
            }
            if(archive==null || !BuildConfig.APPLICATION_ID.equals(archive.packageName)) throw new UpdateFailure("package_mismatch");
            long archived=Build.VERSION.SDK_INT>=28?archive.getLongVersionCode():archive.versionCode;
            if(archived<=BuildConfig.VERSION_CODE || archived!=expectedVersion || !expectedName.equals(archive.versionName)) throw new UpdateFailure("version_mismatch");
            Signature[] a, b;
            if(Build.VERSION.SDK_INT>=28) {
                if(installed.signingInfo==null || archive.signingInfo==null) throw new UpdateFailure("signature_mismatch");
                a=installed.signingInfo.getApkContentsSigners(); b=archive.signingInfo.getApkContentsSigners();
            }
            else { a=installed.signatures; b=archive.signatures; }
            if(a==null || b==null || a.length!=1 || b.length!=1 || !MessageDigest.isEqual(certDigest(installed,a[0]),certDigest(archive,b[0]))) throw new UpdateFailure("signature_mismatch");
        }
        private byte[] certDigest(PackageInfo ignored, Signature signature) throws Exception {
            X509Certificate cert=(X509Certificate)CertificateFactory.getInstance("X.509").generateCertificate(new java.io.ByteArrayInputStream(signature.toByteArray()));
            return MessageDigest.getInstance("SHA-256").digest(cert.getEncoded());
        }
        private String updateError(String kind) {
            String message;
            switch(kind) {
                case "invalid_url": message="Недопустимая ссылка или перенаправление обновления."; break;
                case "size_limit": message="Размер APK превышает 100 MiB."; break;
                case "checksum_mismatch": message="Контрольная сумма APK не совпала."; break;
                case "package_mismatch": message="Файл предназначен для другого приложения."; break;
                case "version_mismatch": message="Версия APK не соответствует обновлению или не является новой."; break;
                case "signature_mismatch": message="Подпись APK не совпадает с установленной PORTAL."; break;
                case "permission_required": message="Разрешите PORTAL устанавливать приложения в настройках Android и повторите установку."; break;
                case "no_installer": message="На устройстве не найден установщик приложений."; break;
                default: message="Не удалось загрузить APK. Проверьте сеть и повторите попытку.";
            }
            try{return new JSONObject().put("ok",false).put("errorCode",kind).put("error",message).toString();}catch(Exception e){return "{\"ok\":false}";}
        }
        private void launchInstaller(String id, File apk) {
            try {
                if(Build.VERSION.SDK_INT>=26 && !context.getPackageManager().canRequestPackageInstalls()) {
                    Intent settings=new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:"+context.getPackageName()));
                    context.startActivity(settings); deliver(id,updateError("permission_required")); return;
                }
                Uri uri=FileProvider.getUriForFile(context,BuildConfig.APPLICATION_ID+".files",apk);
                Intent install=new Intent(Intent.ACTION_VIEW); install.setDataAndType(uri,"application/vnd.android.package-archive");
                install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); context.startActivity(install);
                deliver(id,"{\"ok\":true,\"state\":\"ready\"}");
            } catch(android.content.ActivityNotFoundException e) { deliver(id,updateError("no_installer")); }
            catch(Exception e) { deliver(id,updateError("network")); }
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

        private boolean isLegacyLocalServer(String value) {
            if (value == null || value.trim().isEmpty()) return true;
            try {
                URL url = new URL(value.trim());
                String host = url.getHost() == null ? "" : url.getHost().toLowerCase(Locale.ROOT);
                return "127.0.0.1".equals(host) || "localhost".equals(host) || "portal.invalid".equals(host);
            } catch (Exception ignored) {
                return true;
            }
        }

        @JavascriptInterface
        public String getServerUrl() {
            String saved = prefs.getString("server_url", "");
            if (isLegacyLocalServer(saved) && DEFAULT_URL != null && DEFAULT_URL.startsWith("https://")) {
                prefs.edit().remove("server_url").apply();
                return DEFAULT_URL;
            }
            return saved == null || saved.trim().isEmpty() ? DEFAULT_URL : saved;
        }

        @JavascriptInterface
        public void setServerUrl(String value) {
            if (value == null) return;
            value = value.trim();
            while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
            try {
                URL url = new URL(value);
                if (isSafeServerTransport(url) && url.getUserInfo() == null
                        && url.getQuery() == null && url.getRef() == null && (url.getPath().isEmpty() || "/".equals(url.getPath()))) {
                    prefs.edit().putString("server_url", value).apply();
                }
            } catch (Exception ignored) { }
        }

        @JavascriptInterface
        public String request(String method, String path, String body, String token) {
            return requestAt(resolveServerForRequest(getServerUrl()), method, path, body, token, "");
        }

        @JavascriptInterface
        public String requestForCompany(String method, String path, String body, String token, String company) {
            return requestAt(resolveServerForRequest(getServerUrl()), method, path, body, token, company);
        }

        private String requestAt(String base, String method, String path, String body, String token, String company) {
            HttpURLConnection conn = null;
            try {
                if (path == null || !path.startsWith("/api/") || path.contains("\\") || path.contains("#")) throw new Exception("Некорректный API-путь");
                URL url = new URL(base + path);
                if (!isSafeServerTransport(url)) throw new Exception("Небезопасный адрес сервера");
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
                int responseLimit = path.startsWith("/api/v3/document-file") ? 30 * 1024 * 1024
                        : path.startsWith("/api/v3/chat-file") ? 4 * 1024 * 1024
                        : 2 * 1024 * 1024;
                JSONObject result = new JSONObject(readLimited(stream, responseLimit));
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
