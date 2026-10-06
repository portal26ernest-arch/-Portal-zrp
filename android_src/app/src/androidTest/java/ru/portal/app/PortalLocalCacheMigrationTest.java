package ru.portal.app;

import android.test.AndroidTestCase;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class PortalLocalCacheMigrationTest extends AndroidTestCase {
    public void testOriginMigrationKeepsActiveQueueWholeAfterInjectedFailureAndRetries() throws Exception {
        String suffix = Long.toString(System.nanoTime());
        String oldOrigin = "https://migration-old-" + suffix + ".example";
        String newOrigin = "https://migration-new-" + suffix + ".example";
        File base = new File(getContext().getFilesDir(), "company-outbox");
        File source = new File(new File(base, hash(oldOrigin.toLowerCase())), "17");
        File target = new File(new File(base, hash(newOrigin.toLowerCase())), "17");
        source.mkdirs();
        try {
            write(new File(source, "request-a.bin"), "durable-a");
            write(new File(source, "request-b.bin"), "durable-b");

            PortalLocalCache cache = new PortalLocalCache(getContext());
            assertFalse(cache.migrateOutboxOrigin(oldOrigin, newOrigin, 1));
            assertEquals("failed migration changed active origin queue", 2, binCount(source));
            assertEquals("fault injection should stop after first staged copy", 1, binCount(target));

            assertTrue("retry should complete migration", cache.migrateOutboxOrigin(oldOrigin, newOrigin));
            assertEquals("target queue lost or duplicated work", 2, binCount(target));
            assertFalse("old active-origin queue should be cleaned after successful copy", source.exists());
        } finally {
            deleteTree(new File(base, hash(oldOrigin.toLowerCase())));
            deleteTree(new File(base, hash(newOrigin.toLowerCase())));
        }
    }

    private static int binCount(File dir) {
        File[] rows = dir.listFiles((parent, name) -> name.endsWith(".bin"));
        return rows == null ? 0 : rows.length;
    }

    private void write(File file, String text) throws Exception {
        assertTrue(file.getParentFile().isDirectory() || file.getParentFile().mkdirs());
        try (java.io.FileOutputStream out = new java.io.FileOutputStream(file)) {
            out.write(text.getBytes(StandardCharsets.UTF_8));
            out.getFD().sync();
        }
    }

    private static String hash(String value) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder result = new StringBuilder(digest.length * 2);
        for (byte item : digest) result.append(String.format(java.util.Locale.ROOT, "%02x", item & 0xff));
        return result.toString();
    }

    private static void deleteTree(File file) {
        File[] children = file.listFiles();
        if (children != null) for (File child : children) deleteTree(child);
        if (file.exists()) file.delete();
    }
}
