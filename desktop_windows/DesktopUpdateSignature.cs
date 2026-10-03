using System.Security.Cryptography;
using System.Text;

namespace Portal.Desktop;

internal sealed record DesktopUpdateManifest(int Build, string Version, string DownloadUrl, string Sha256, string Signature);

internal static class DesktopUpdateSignature
{
    private static readonly Lazy<string> PinnedPublicKey = new(LoadPinnedPublicKey);

    internal static byte[] CreatePayload(DesktopUpdateManifest manifest) => CreatePayload(
        manifest.Build, manifest.Version, manifest.DownloadUrl, manifest.Sha256);

    internal static byte[] CreatePayload(int build, string version, string downloadUrl, string sha256) =>
        Encoding.UTF8.GetBytes($"PORTAL-DESKTOP-UPDATE-V1\n{build}\n{version}\n{downloadUrl}\n{sha256.ToLowerInvariant()}\n");

    internal static bool Verify(DesktopUpdateManifest manifest) => Verify(
        CreatePayload(manifest), manifest.Signature, PinnedPublicKey.Value);

    private static string LoadPinnedPublicKey()
    {
        using var stream = typeof(DesktopUpdateSignature).Assembly
            .GetManifestResourceStream("Portal.Desktop.desktop-update-signing-public.pem")
            ?? throw new CryptographicException("Pinned Desktop update key is missing.");
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    internal static bool Verify(byte[] payload, string? signatureText, string publicKeyPem)
    {
        try
        {
            var signature = Convert.FromBase64String(signatureText ?? string.Empty);
            if (signature.Length != 384) return false;
            using var rsa = RSA.Create();
            rsa.ImportFromPem(publicKeyPem);
            return rsa.VerifyData(payload, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        }
        catch (FormatException) { return false; }
        catch (CryptographicException) { return false; }
    }
}
