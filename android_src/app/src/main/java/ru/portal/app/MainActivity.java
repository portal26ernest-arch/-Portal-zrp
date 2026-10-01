package ru.portal.app;

import android.annotation.SuppressLint;
import android.app.Activity;
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

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 42032;
    private WebView webView;
    private PortalBridge bridge;
    private ValueCallback<Uri[]> filePathCallback;

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
        private final ExecutorService executor = Executors.newFixedThreadPool(3);
        private volatile boolean closed;
        private static final String DEFAULT_URL = BuildConfig.DEFAULT_API_URL;

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
