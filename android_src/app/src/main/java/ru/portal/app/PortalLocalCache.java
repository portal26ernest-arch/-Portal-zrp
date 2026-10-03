package ru.portal.app;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Locale;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Device-local encrypted snapshot cache. Server data remains the sync authority. */
final class PortalLocalCache {
    private static final String KEY_ALIAS = "portal-local-cache-v1";
    private static final int MAX_PAYLOAD = 8 * 1024 * 1024;
    private static final int MAX_OUTBOX_ITEM = 512 * 1024;
    private static final int MAX_OUTBOX_ITEMS = 1000;
    private static final int IV_BYTES = 12;
    private final Context context;
    private final SecureRandom random = new SecureRandom();

    PortalLocalCache(Context context) {
        this.context = context.getApplicationContext();
    }

    String read(String serverOrigin, String companyId, String cacheKey) {
        try {
            File file = cacheFile(serverOrigin, companyId, cacheKey);
            if (file == null || !file.isFile() || file.length() > MAX_PAYLOAD * 2L) return "";
            byte[] all = readLimited(file, MAX_PAYLOAD * 2);
            if (all.length <= 1 + IV_BYTES || all[0] != 1) return "";
            byte[] iv = new byte[IV_BYTES];
            System.arraycopy(all, 1, iv, 0, IV_BYTES);
            byte[] encrypted = new byte[all.length - 1 - IV_BYTES];
            System.arraycopy(all, 1 + IV_BYTES, encrypted, 0, encrypted.length);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            byte[] plain = cipher.doFinal(encrypted);
            if (plain.length > MAX_PAYLOAD) return "";
            return new String(plain, StandardCharsets.UTF_8);
        } catch (Exception ignored) {
            return "";
        }
    }

    boolean write(String serverOrigin, String companyId, String cacheKey, String responseJson) {
        try {
            JSONObject data = new JSONObject(responseJson);
            if (!data.optBoolean("ok", false)) return false;
            JSONObject envelope = new JSONObject()
                    .put("v", 1)
                    .put("key", cacheKey)
                    .put("savedAt", System.currentTimeMillis())
                    .put("data", data);
            byte[] plain = envelope.toString().getBytes(StandardCharsets.UTF_8);
            if (plain.length == 0 || plain.length > MAX_PAYLOAD) return false;
            byte[] iv = new byte[IV_BYTES];
            random.nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            byte[] encrypted = cipher.doFinal(plain);
            File file = cacheFile(serverOrigin, companyId, cacheKey);
            if (file == null) return false;
            File dir = file.getParentFile();
            if (dir == null || (!dir.isDirectory() && !dir.mkdirs())) return false;
            File temp = new File(file.getAbsolutePath() + ".tmp");
            try (FileOutputStream out = new FileOutputStream(temp)) {
                out.write(1);
                out.write(iv);
                out.write(encrypted);
                out.getFD().sync();
            }
            if (file.exists() && !file.delete()) { temp.delete(); return false; }
            if (!temp.renameTo(file)) { temp.delete(); return false; }
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    boolean clearCompany(String serverOrigin, String companyId) {
        try {
            File dir = companyDir(serverOrigin, companyId);
            return dir == null || !dir.exists() || deleteRecursively(dir);
        } catch (Exception ignored) {
            return false;
        }
    }


    boolean enqueueMutation(String serverOrigin, String companyId, String requestId, String json) {
        try {
            if (requestId == null || !requestId.matches("[0-9a-fA-F-]{36}") || json == null) return false;
            byte[] plain = json.getBytes(StandardCharsets.UTF_8);
            if (plain.length == 0 || plain.length > MAX_OUTBOX_ITEM) return false;
            File dir = outboxDir(serverOrigin, companyId);
            if (dir == null || (!dir.isDirectory() && !dir.mkdirs())) return false;
            File[] existing = dir.listFiles((d, name) -> name.endsWith(".bin"));
            if (existing != null && existing.length >= MAX_OUTBOX_ITEMS) return false;
            byte[] encoded = encryptRaw(plain);
            File target = new File(dir, hash(requestId) + ".bin");
            File temp = new File(target.getAbsolutePath() + ".tmp");
            try (FileOutputStream out = new FileOutputStream(temp)) {
                out.write(encoded);
                out.getFD().sync();
            }
            if (target.exists() && !target.delete()) { temp.delete(); return false; }
            if (!temp.renameTo(target)) { temp.delete(); return false; }
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    String pendingMutations(String serverOrigin, String companyId) {
        JSONArray rows = new JSONArray();
        try {
            File dir = outboxDir(serverOrigin, companyId);
            if (dir == null || !dir.isDirectory()) return rows.toString();
            File[] files = dir.listFiles((d, name) -> name.endsWith(".bin"));
            if (files == null) return rows.toString();
            Arrays.sort(files, Comparator.comparingLong(File::lastModified));
            for (File file : files) {
                try {
                    byte[] plain = decryptRaw(readLimited(file, MAX_OUTBOX_ITEM * 2), MAX_OUTBOX_ITEM);
                    if (plain.length > 0) rows.put(new String(plain, StandardCharsets.UTF_8));
                } catch (Exception ignored) { }
            }
        } catch (Exception ignored) { }
        return rows.toString();
    }

    boolean removeMutation(String serverOrigin, String companyId, String requestId) {
        try {
            if (requestId == null || !requestId.matches("[0-9a-fA-F-]{36}")) return false;
            File dir = outboxDir(serverOrigin, companyId);
            if (dir == null) return false;
            File target = new File(dir, hash(requestId) + ".bin");
            return !target.exists() || target.delete();
        } catch (Exception ignored) {
            return false;
        }
    }

    int pendingMutationCount(String serverOrigin, String companyId) {
        try {
            File dir = outboxDir(serverOrigin, companyId);
            File[] files = dir == null ? null : dir.listFiles((d, name) -> name.endsWith(".bin"));
            return files == null ? 0 : files.length;
        } catch (Exception ignored) {
            return 0;
        }
    }

    private File outboxDir(String serverOrigin, String companyId) throws Exception {
        if (serverOrigin == null || serverOrigin.isBlank() || companyId == null || !companyId.matches("[1-9][0-9]{0,9}")) return null;
        return new File(new File(new File(context.getFilesDir(), "company-outbox"), hash(serverOrigin.toLowerCase(Locale.ROOT))), companyId);
    }

    private byte[] encryptRaw(byte[] plain) throws Exception {
        byte[] iv = new byte[IV_BYTES];
        random.nextBytes(iv);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        byte[] encrypted = cipher.doFinal(plain);
        byte[] result = new byte[1 + IV_BYTES + encrypted.length];
        result[0] = 1;
        System.arraycopy(iv, 0, result, 1, IV_BYTES);
        System.arraycopy(encrypted, 0, result, 1 + IV_BYTES, encrypted.length);
        return result;
    }

    private byte[] decryptRaw(byte[] all, int maxPlain) throws Exception {
        if (all == null || all.length <= 1 + IV_BYTES || all.length > maxPlain * 2L || all[0] != 1) return new byte[0];
        byte[] iv = new byte[IV_BYTES];
        System.arraycopy(all, 1, iv, 0, IV_BYTES);
        byte[] encrypted = new byte[all.length - 1 - IV_BYTES];
        System.arraycopy(all, 1 + IV_BYTES, encrypted, 0, encrypted.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
        byte[] plain = cipher.doFinal(encrypted);
        return plain.length <= maxPlain ? plain : new byte[0];
    }

    private File cacheFile(String serverOrigin, String companyId, String cacheKey) throws Exception {
        File dir = companyDir(serverOrigin, companyId);
        if (dir == null || cacheKey == null || cacheKey.isBlank() || cacheKey.length() > 2048) return null;
        return new File(dir, hash(cacheKey) + ".bin");
    }

    private File companyDir(String serverOrigin, String companyId) throws Exception {
        if (serverOrigin == null || serverOrigin.isBlank() || companyId == null || !companyId.matches("[1-9][0-9]{0,9}")) return null;
        return new File(new File(new File(context.getFilesDir(), "company-cache"), hash(serverOrigin.toLowerCase(Locale.ROOT))), companyId);
    }


    private static byte[] readLimited(File file, int limit) throws Exception {
        try (FileInputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[16384];
            int read;
            while ((read = in.read(buffer)) != -1) {
                if (out.size() + read > limit) throw new IllegalArgumentException("cache size limit");
                out.write(buffer, 0, read);
            }
            return out.toByteArray();
        }
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        KeyStore.Entry existing = store.getEntry(KEY_ALIAS, null);
        if (existing instanceof KeyStore.SecretKeyEntry) return ((KeyStore.SecretKeyEntry) existing).getSecretKey();
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return generator.generateKey();
    }

    private static String hash(String value) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder out = new StringBuilder(digest.length * 2);
        for (byte b : digest) out.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return out.toString();
    }

    private static boolean deleteRecursively(File file) {
        File[] children = file.listFiles();
        if (children != null) for (File child : children) if (!deleteRecursively(child)) return false;
        return file.delete();
    }
}
