using System.Security.Cryptography;
using System.Text;
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
