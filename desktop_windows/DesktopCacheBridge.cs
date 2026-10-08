using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Portal.Desktop;

[ComVisible(true)]
[ClassInterface(ClassInterfaceType.AutoDual)]
public sealed class DesktopCacheBridge
{
    private const int MaxPayloadBytes = 12 * 1024 * 1024;
    private const int MaxOutboxItemBytes = 512 * 1024;
    private const int MaxOutboxItems = 1000;
    private readonly string _root;
    private readonly string _outboxRoot;

    public DesktopCacheBridge(string settingsDir, string serverOrigin)
    {
        var originKey = OriginKey(serverOrigin);
        _root = Path.Combine(settingsDir, "company-cache", originKey);
        _outboxRoot = Path.Combine(settingsDir, "company-outbox", originKey);
        Directory.CreateDirectory(_root);
        Directory.CreateDirectory(_outboxRoot);
    }

    public string Read(string cacheScope, string cacheKey)
    {
        try
        {
            var path = CachePath(cacheScope, cacheKey);
            if (path is null || !File.Exists(path)) return string.Empty;
            var encrypted = File.ReadAllBytes(path);
            if (encrypted.Length > MaxPayloadBytes * 2) return string.Empty;
            var plain = ProtectedData.Unprotect(
                encrypted,
                optionalEntropy: null,
                scope: DataProtectionScope.CurrentUser);
            if (plain.Length > MaxPayloadBytes) return string.Empty;
            return Encoding.UTF8.GetString(plain);
        }
        catch
        {
            return string.Empty;
        }
    }

    public bool Write(string cacheScope, string cacheKey, string json)
    {
        try
        {
            var path = CachePath(cacheScope, cacheKey);
            if (path is null || string.IsNullOrWhiteSpace(json)) return false;
            var plain = Encoding.UTF8.GetBytes(json);
            if (plain.Length > MaxPayloadBytes) return false;
            var encrypted = ProtectedData.Protect(
                plain,
                optionalEntropy: null,
                scope: DataProtectionScope.CurrentUser);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var temp = path + ".tmp";
            File.WriteAllBytes(temp, encrypted);
            File.Move(temp, path, overwrite: true);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public bool ClearCompany(string cacheScope)
    {
        try
        {
            var scopeDir = CacheScopeDirectory(cacheScope);
            if (scopeDir is null || !Directory.Exists(scopeDir)) return true;
            Directory.Delete(scopeDir, recursive: true);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public bool Delete(string cacheScope, string cacheKey)
    {
        try
        {
            var path = CachePath(cacheScope, cacheKey);
            if (path is null || !File.Exists(path)) return true;
            File.Delete(path);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public bool MarkStale(string cacheScope, string keysJson)
    {
        try
        {
            var dir = CacheScopeDirectory(cacheScope);
            if (dir is null || !Directory.Exists(dir) || string.IsNullOrWhiteSpace(keysJson)) return false;
            var keys = JsonSerializer.Deserialize<string[]>(keysJson) ?? Array.Empty<string>();
            if (keys.Length == 0 || keys.Length > 64) return false;
            foreach (var path in Directory.GetFiles(dir, "*.bin"))
            {
                try
                {
                    var encrypted = File.ReadAllBytes(path);
                    if (encrypted.Length > MaxPayloadBytes * 2) continue;
                    var plain = ProtectedData.Unprotect(encrypted, optionalEntropy: null, scope: DataProtectionScope.CurrentUser);
                    using var document = JsonDocument.Parse(plain);
                    var root = document.RootElement;
                    if (!root.TryGetProperty("key", out var keyNode)) continue;
                    var key = keyNode.GetString() ?? string.Empty;
                    if (!keys.Any(prefix => key.Equals(prefix, StringComparison.Ordinal) || key.StartsWith(prefix + "?", StringComparison.Ordinal))) continue;

                    var map = JsonSerializer.Deserialize<Dictionary<string, object?>>(plain) ?? new();
                    map["staleAt"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                    var updated = JsonSerializer.SerializeToUtf8Bytes(map);
                    if (updated.Length > MaxPayloadBytes) continue;
                    var protectedBytes = ProtectedData.Protect(updated, optionalEntropy: null, scope: DataProtectionScope.CurrentUser);
                    var temp = path + ".tmp";
                    File.WriteAllBytes(temp, protectedBytes);
                    File.Move(temp, path, overwrite: true);
                }
                catch { }
            }
            return true;
        }
        catch
        {
            return false;
        }
    }

    public bool ClearAll()
    {
        try
        {
            if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
            Directory.CreateDirectory(_root);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public bool EnqueueMutation(string companyId, string userId, string requestId, string json)
    {
        try
        {
            var dir = OutboxDirectory(companyId, userId);
            if (dir is null || !Guid.TryParse(requestId, out _) || string.IsNullOrWhiteSpace(json)) return false;
            Directory.CreateDirectory(dir);
            RecoverOutboxTemps(dir);
            if (Directory.GetFiles(dir, "*.bin").Length >= MaxOutboxItems) return false;
            var plain = Encoding.UTF8.GetBytes(json);
            if (plain.Length == 0 || plain.Length > MaxOutboxItemBytes) return false;
            var encrypted = ProtectedData.Protect(plain, optionalEntropy: null, scope: DataProtectionScope.CurrentUser);
            var path = Path.Combine(dir, Hash(requestId) + ".bin");
            var temp = path + ".tmp";
            File.WriteAllBytes(temp, encrypted);
            File.Move(temp, path, overwrite: true);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public string PendingMutations(string companyId, string userId)
    {
        try
        {
            var dir = OutboxDirectory(companyId, userId);
            if (dir is null || !Directory.Exists(dir)) return "[]";
            RecoverOutboxTemps(dir);
            var rows = new List<string>();
            foreach (var path in Directory.GetFiles(dir, "*.bin").OrderBy(File.GetCreationTimeUtc))
            {
                try
                {
                    var encrypted = File.ReadAllBytes(path);
                    if (encrypted.Length > MaxOutboxItemBytes * 2) continue;
                    var plain = ProtectedData.Unprotect(encrypted, optionalEntropy: null, scope: DataProtectionScope.CurrentUser);
                    if (plain.Length == 0 || plain.Length > MaxOutboxItemBytes) continue;
                    rows.Add(Encoding.UTF8.GetString(plain));
                }
                catch { }
            }
            return JsonSerializer.Serialize(rows);
        }
        catch
        {
            return "[]";
        }
    }

    public bool RemoveMutation(string companyId, string userId, string requestId)
    {
        try
        {
            var dir = OutboxDirectory(companyId, userId);
            if (dir is null || !Guid.TryParse(requestId, out _)) return false;
            var path = Path.Combine(dir, Hash(requestId) + ".bin");
            var temp = path + ".tmp";
            if (File.Exists(path)) File.Delete(path);
            if (File.Exists(temp)) File.Delete(temp);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public int PendingMutationCount(string companyId, string userId)
    {
        try
        {
            var dir = OutboxDirectory(companyId, userId);
            if (dir is null || !Directory.Exists(dir)) return 0;
            RecoverOutboxTemps(dir);
            return Directory.GetFiles(dir, "*.bin").Length;
        }
        catch
        {
            return 0;
        }
    }

    public static bool MigrateOutboxOrigin(string settingsDir, string oldOrigin, string newOrigin)
        => MigrateOutboxOrigin(settingsDir, oldOrigin, newOrigin, null);

    internal static bool MigrateOutboxOrigin(string settingsDir, string oldOrigin, string newOrigin, Action<int>? afterCopy)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(oldOrigin) || string.IsNullOrWhiteSpace(newOrigin) ||
                oldOrigin.Equals(newOrigin, StringComparison.OrdinalIgnoreCase)) return true;
            var baseDir = Path.Combine(settingsDir, "company-outbox");
            var source = Path.Combine(baseDir, OriginKey(oldOrigin));
            if (!Directory.Exists(source)) return true;
            var target = Path.Combine(baseDir, OriginKey(newOrigin));
            Directory.CreateDirectory(target);

            foreach (var directory in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
                RecoverOutboxTemps(directory);

            var copied = 0;
            foreach (var row in Directory.GetFiles(source, "*.bin", SearchOption.AllDirectories))
            {
                var relative = Path.GetRelativePath(source, row);
                var parts = relative.Split(
                    new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar },
                    StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length is < 2 or > 3 ||
                    !long.TryParse(parts[0], out var companyId) || companyId < 1 ||
                    (parts.Length == 3 && (!long.TryParse(parts[1], out var userId) || userId < 1)))
                    return false;

                var destination = Path.Combine(target, relative);
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                if (File.Exists(destination))
                {
                    if (!File.ReadAllBytes(row).SequenceEqual(File.ReadAllBytes(destination))) return false;
                    continue;
                }

                var temp = destination + ".migrating";
                if (File.Exists(temp)) File.Delete(temp);
                File.Copy(row, temp, overwrite: false);
                File.Move(temp, destination);
                copied++;
                afterCopy?.Invoke(copied);
            }

            // Complete and verify the target copy before callers switch the stored origin.
            foreach (var row in Directory.GetFiles(source, "*.bin", SearchOption.AllDirectories))
            {
                var destination = Path.Combine(target, Path.GetRelativePath(source, row));
                if (!File.Exists(destination) ||
                    !File.ReadAllBytes(row).SequenceEqual(File.ReadAllBytes(destination))) return false;
            }

            // Source cleanup is best effort; a retry remains safe because every target row was verified.
            try { Directory.Delete(source, recursive: true); } catch { }
            return true;
        }
        catch
        {
            return false;
        }
    }

    private string? OutboxDirectory(string companyId, string userId)
    {
        if (!long.TryParse(companyId, out var company) || company < 1 ||
            !long.TryParse(userId, out var user) || user < 1) return null;
        return Path.Combine(_outboxRoot, company.ToString(), user.ToString());
    }

    private static void RecoverOutboxTemps(string dir)
    {
        if (!Directory.Exists(dir)) return;
        foreach (var temp in Directory.GetFiles(dir, "*.bin.tmp"))
        {
            try
            {
                var target = temp[..^4];
                if (File.Exists(target))
                {
                    File.Delete(temp);
                    continue;
                }
                var encrypted = File.ReadAllBytes(temp);
                if (encrypted.Length == 0 || encrypted.Length > MaxOutboxItemBytes * 2) continue;
                var plain = ProtectedData.Unprotect(encrypted, optionalEntropy: null, scope: DataProtectionScope.CurrentUser);
                if (plain.Length == 0 || plain.Length > MaxOutboxItemBytes) continue;
                using var document = JsonDocument.Parse(plain);
                if (!document.RootElement.TryGetProperty("request_id", out var requestNode) ||
                    !Guid.TryParse(requestNode.GetString(), out var requestId)) continue;
                var expected = Path.Combine(dir, Hash(requestId.ToString()) + ".bin");
                if (!target.Equals(expected, StringComparison.OrdinalIgnoreCase)) continue;
                File.Move(temp, target);
            }
            catch { }
        }
    }

    private static string OriginKey(string serverOrigin)
        => Hash((serverOrigin ?? string.Empty).Trim().TrimEnd('/').ToLowerInvariant());

    private string? CachePath(string cacheScope, string cacheKey)
    {
        var dir = CacheScopeDirectory(cacheScope);
        if (dir is null || string.IsNullOrWhiteSpace(cacheKey) || cacheKey.Length > 2048) return null;
        return Path.Combine(dir, Hash(cacheKey) + ".bin");
    }

    private string? CacheScopeDirectory(string cacheScope)
    {
        if (string.IsNullOrWhiteSpace(cacheScope) || cacheScope.Length > 2048) return null;
        var parts = cacheScope.Split('|', 4);
        if (parts.Length != 4 || !long.TryParse(parts[0], out var companyId) || companyId < 1 ||
            !long.TryParse(parts[1], out var userId) || userId < 1) return null;
        var role = parts[2];
        var permissions = parts[3];
        if (role.Length is < 2 or > 40 || role.Any(c => !(char.IsAsciiLetterLower(c) || c == '_'))) return null;
        if (permissions.Length > 1500 || permissions.Any(c => !(char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or '-' or ','))) return null;
        return Path.Combine(_root, companyId.ToString(), Hash(cacheScope));
    }

    private static string Hash(string value)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
