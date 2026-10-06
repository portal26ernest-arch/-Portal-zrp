using System.Security.Cryptography;
using System.Text;
using System.IO;
using System.Linq;
using Portal.Desktop;

using var signer = RSA.Create(3072);
using var otherSigner = RSA.Create(3072);
var publicKey = signer.ExportSubjectPublicKeyInfoPem();
var manifest = new DesktopUpdateManifest(45, "4.5.0",
    "https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-desktop-v4.5.0/PORTAL-Desktop-win-x64-4.5.0.zip",
    new string('a', 64), string.Empty);
var payload = DesktopUpdateSignature.CreatePayload(manifest);
var expectedPayload = Encoding.UTF8.GetBytes(
    "PORTAL-DESKTOP-UPDATE-V1\n45\n4.5.0\n" + manifest.DownloadUrl + "\n" + new string('a', 64) + "\n");
if (!payload.SequenceEqual(expectedPayload))
    throw new Exception("Desktop update signing payload differs from the release format.");
var signature = Convert.ToBase64String(signer.SignData(payload, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1));
if (!DesktopUpdateSignature.Verify(payload, signature, publicKey))
    throw new Exception("Valid RSA-SHA256 update signature was rejected.");
if (DesktopUpdateSignature.Verify(DesktopUpdateSignature.CreatePayload(manifest with { Sha256 = new string('b', 64) }),
        signature, publicKey))
    throw new Exception("A modified package digest passed signature verification.");
if (DesktopUpdateSignature.Verify(payload, signature, otherSigner.ExportSubjectPublicKeyInfoPem()))
    throw new Exception("A signature from an untrusted key was accepted.");
if (DesktopUpdateSignature.Verify(payload, "unsigned", publicKey))
    throw new Exception("Malformed signature was accepted.");

Console.WriteLine("Desktop update signature verification: OK");

var migrationRoot = Path.Combine(Path.GetTempPath(), "portal-outbox-migration-test-" + Guid.NewGuid().ToString("N"));
try
{
    const string oldOrigin = "https://api.vart-portal.ru";
    const string newOrigin = "https://reserve-api.vart-portal.ru";
    var source = Path.Combine(migrationRoot, "company-outbox", Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(oldOrigin.ToLowerInvariant()))).ToLowerInvariant(), "17");
    Directory.CreateDirectory(source);
    File.WriteAllText(Path.Combine(source, "request-a.bin"), "durable-a");
    File.WriteAllText(Path.Combine(source, "request-b.bin"), "durable-b");

    var injected = false;
    var failed = DesktopCacheBridge.MigrateOutboxOrigin(migrationRoot, oldOrigin, newOrigin, copied =>
    {
        if (copied == 1) { injected = true; throw new IOException("injected copy failure"); }
    });
    if (failed || !injected) throw new Exception("Outbox migration fault injection did not fail after the first copy.");
    if (Directory.GetFiles(source, "*.bin").Length != 2)
        throw new Exception("Failed outbox migration changed the active origin queue.");
    var target = Path.Combine(migrationRoot, "company-outbox", Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(newOrigin.ToLowerInvariant()))).ToLowerInvariant(), "17");
    if (Directory.GetFiles(target, "*.bin").Length != 1)
        throw new Exception("Fault injection did not leave exactly one staged target copy.");
    if (!DesktopCacheBridge.MigrateOutboxOrigin(migrationRoot, oldOrigin, newOrigin))
        throw new Exception("Retry did not complete the outbox migration.");
    if (Directory.GetFiles(target, "*.bin").Length != 2 || Directory.Exists(source))
        throw new Exception("Retried outbox migration lost or duplicated queued work.");
}
finally
{
    if (Directory.Exists(migrationRoot)) Directory.Delete(migrationRoot, recursive: true);
}
Console.WriteLine("Desktop outbox migration rollback and retry: OK");
