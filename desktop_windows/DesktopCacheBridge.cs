using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace Portal.Desktop;

[ComVisible(true)]
[ClassInterface(ClassInterfaceType.AutoDual)]
public sealed class DesktopCacheBridge
{
    private const int MaxPayloadBytes = 12 * 1024 * 1024;
    private readonly string _root;

    public DesktopCacheBridge(string settingsDir, string serverOrigin)
    {
        var originKey = Hash(serverOrigin);
        _root = Path.Combine(settingsDir, "company-cache", originKey);
        Directory.CreateDirectory(_root);
    }

    public string Read(string companyId, string cacheKey)
    {
        try
        {
            var path = CachePath(companyId, cacheKey);
            if (path is null || !File.Exists(path)) return string.Empty;
            var encrypted = File.ReadAllBytes(path);
            if (encrypted.Length > MaxPayloadBytes * 2) return string.Empty;            var plain = ProtectedData.Unprotect(
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

    public bool Write(string companyId, string cacheKey, string json)
    {
        try
        {
            var path = CachePath(companyId, cacheKey);
            if (path is null || string.IsNullOrWhiteSpace(json)) return false;
            var plain = Encoding.UTF8.GetBytes(json);
            if (plain.Length > MaxPayloadBytes) return false;
            var encrypted = ProtectedData.Protect(
                plain,
                optionalEntropy: null,
                scope: DataProtectionScope.CurrentUser);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var temp = path + ".tmp";            File.WriteAllBytes(temp, encrypted);
            File.Move(temp, path, overwrite: true);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public bool ClearCompany(string companyId)
    {
        try
        {
            var companyDir = CompanyDirectory(companyId);
            if (companyDir is null || !Directory.Exists(companyDir)) return true;
            Directory.Delete(companyDir, recursive: true);
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
    private string? CachePath(string companyId, string cacheKey)
    {
        var dir = CompanyDirectory(companyId);
        if (dir is null || string.IsNullOrWhiteSpace(cacheKey) || cacheKey.Length > 2048) return null;
        return Path.Combine(dir, Hash(cacheKey) + ".bin");
    }

    private string? CompanyDirectory(string companyId)
    {
        if (!long.TryParse(companyId, out var id) || id < 1) return null;
        return Path.Combine(_root, id.ToString());
    }

    private static string Hash(string value)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
