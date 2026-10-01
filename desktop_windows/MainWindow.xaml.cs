using Microsoft.Web.WebView2.Core;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Input;

namespace Portal.Desktop;

public partial class MainWindow : Window
{
    private const int CurrentBuild = 38;
    private const long MaxInstallerBytes = 250L * 1024 * 1024;
    private const string GithubRepository = "portal26ernest-arch/-Portal-zrp";
    private static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = false })
    {
        Timeout = TimeSpan.FromMinutes(5)
    };
    private readonly string _settingsDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PORTAL");
    private string? _serverOrigin;
    private bool _browserEventsAttached;
    private bool _webRecoveryPending;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += MainWindow_Loaded;
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        var configured = Environment.GetEnvironmentVariable("PORTAL_SERVER_URL");
        var candidate = string.IsNullOrWhiteSpace(configured) ? LoadStoredOrigin() : configured;
        if (TryNormalizeOrigin(candidate, out var origin, out var error))
        {
            ServerUrlBox.Text = origin;
            await ConnectAsync(origin, persist: false);
            return;
        }

        ShowSetup(candidate is null ? null : error);
    }

    private string? LoadStoredOrigin()
    {
        try
        {
            var path = Path.Combine(_settingsDir, "desktop.json");
            if (!File.Exists(path)) return null;
            return JsonSerializer.Deserialize<DesktopSettings>(File.ReadAllText(path))?.ServerOrigin;
        }
        catch
        {
            return null;
        }
    }

    private void SaveOrigin(string origin)
    {
        Directory.CreateDirectory(_settingsDir);
        var json = JsonSerializer.Serialize(new DesktopSettings(origin), new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(Path.Combine(_settingsDir, "desktop.json"), json);
    }
    private static bool TryNormalizeOrigin(string? raw, out string origin, out string error)
    {
        origin = string.Empty;
        error = "Укажите корректный адрес сервера.";
        if (string.IsNullOrWhiteSpace(raw) || !Uri.TryCreate(raw.Trim(), UriKind.Absolute, out var uri))
            return false;
        if (!string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment))
        {
            error = "Адрес не должен содержать логин, параметры или фрагмент.";
            return false;
        }

        var loopback = uri.IsLoopback || uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase);
        if (!uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) &&
            !(loopback && uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)))
        {
            error = "Разрешён HTTPS; HTTP допускается только для localhost.";
            return false;
        }
        if (uri.AbsolutePath != "/")
        {
            error = "Укажите только адрес сервера без /web и других путей.";
            return false;
        }

        origin = uri.GetLeftPart(UriPartial.Authority).TrimEnd('/');
        return true;
    }
    private async Task ConnectAsync(string origin, bool persist)
    {
        try
        {
            StatusText.Text = "Проверка сервера…";
            var problem = await ProbePortalWebAsync(origin);
            if (problem is not null)
            {
                ShowSetup(problem);
                return;
            }
            StatusText.Text = "Подключение…";
            if (Browser.CoreWebView2 is null)
            {
                Directory.CreateDirectory(_settingsDir);
                var env = await CoreWebView2Environment.CreateAsync(
                    userDataFolder: Path.Combine(_settingsDir, "WebView2"));
                var options = env.CreateCoreWebView2ControllerOptions();
                options.IsInPrivateModeEnabled = true;
                await Browser.EnsureCoreWebView2Async(env, options);
                ConfigureBrowser();
            }
            _serverOrigin = origin;
            if (persist) SaveOrigin(origin);
            SetupPanel.Visibility = Visibility.Collapsed;
            Browser.Visibility = Visibility.Visible;
            Browser.Source = new Uri(origin + "/web/");
        }
        catch (WebView2RuntimeNotFoundException)
        {
            ShowSetup("Не найден Microsoft Edge WebView2 Runtime. Установите официальный WebView2 Runtime и повторите запуск.");
        }
        catch (OperationCanceledException)
        {
            ShowSetup("Сервер PORTAL не ответил за 12 секунд. Проверьте сеть и адрес.");
        }
        catch (HttpRequestException)
        {
            ShowSetup("Не удалось установить соединение с сервером. Проверьте сеть, HTTPS и сертификат.");
        }
        catch
        {
            ShowSetup("Не удалось открыть PORTAL. Проверьте адрес сервера и соединение.");
        }
    }

    private static async Task<string?> ProbePortalWebAsync(string origin)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(12));
        using var response = await Http.GetAsync(origin + "/web/", HttpCompletionOption.ResponseHeadersRead,
            timeout.Token);
        if ((int)response.StatusCode is >= 300 and < 400)
            return "Сервер перенаправляет /web/. Укажите окончательный HTTPS-адрес PORTAL.";
        if (response.StatusCode != HttpStatusCode.OK)
            return $"Сервер ответил HTTP {(int)response.StatusCode} на /web/. Проверьте адрес и настройку PORTAL Web.";
        if (!string.Equals(response.Content.Headers.ContentType?.MediaType, "text/html",
                StringComparison.OrdinalIgnoreCase))
            return "По адресу /web/ сервер не отдаёт интерфейс PORTAL (HTML).";
        return null;
    }

    private void ConfigureBrowser()
    {
        if (Browser.CoreWebView2 is null) return;
        Browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
        Browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
        Browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
        Browser.CoreWebView2.Settings.IsPasswordAutosaveEnabled = false;
        if (_browserEventsAttached) return;
        Browser.CoreWebView2.NavigationStarting += (_, e) =>
        {
            if (e.Uri == "about:blank") return;
            if (_serverOrigin is null || !Uri.TryCreate(e.Uri, UriKind.Absolute, out var target))
            {
                e.Cancel = true;
                return;
            }
            if (SameOrigin(target, _serverOrigin)) return;
            e.Cancel = true;
            OpenExternalHttps(target);
        };
        Browser.CoreWebView2.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            if (_serverOrigin is not null && Uri.TryCreate(e.Uri, UriKind.Absolute, out var target))
            {
                if (SameOrigin(target, _serverOrigin)) Browser.Source = target;
                else OpenExternalHttps(target);
            }
        };
        Browser.CoreWebView2.NavigationCompleted += (_, e) =>
        {
            if (_serverOrigin is null || Browser.Visibility != Visibility.Visible) return;
            StatusText.Text = e.IsSuccess ? "Подключено" : "Ошибка подключения";
            BackButton.IsEnabled = true;
            _webRecoveryPending = false;
        };
        Browser.CoreWebView2.ProcessFailed += (_, _) =>
        {
            if (_webRecoveryPending || Browser.Visibility != Visibility.Visible) return;
            _webRecoveryPending = true;
            StatusText.Text = "Восстанавливаем интерфейс…";
            _ = Dispatcher.InvokeAsync(async () =>
            {
                await Task.Delay(350);
                if (Browser.Visibility == Visibility.Visible) Browser.Reload();
            });
        };
        _browserEventsAttached = true;
    }

    private static bool SameOrigin(Uri target, string origin) =>
        target.GetLeftPart(UriPartial.Authority).Equals(origin, StringComparison.OrdinalIgnoreCase);

    private static void OpenExternalHttps(Uri target)
    {
        if (!target.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)) return;
        Process.Start(new ProcessStartInfo(target.AbsoluteUri) { UseShellExecute = true });
    }
    private async void Connect_Click(object sender, RoutedEventArgs e)
    {
        SetupError.Text = string.Empty;
        if (!TryNormalizeOrigin(ServerUrlBox.Text, out var origin, out var error))
        {
            SetupError.Text = error;
            return;
        }
        await ConnectAsync(origin, persist: true);
    }

    private async void Server_Click(object sender, RoutedEventArgs e)
    {
        ShowSetup();
        if (Browser.CoreWebView2 is null) return;
        ConnectButton.IsEnabled = false;
        StatusText.Text = "Очистка сеанса…";
        _serverOrigin = null;
        try
        {
            Browser.CoreWebView2.Navigate("about:blank");
            await Browser.CoreWebView2.Profile.ClearBrowsingDataAsync();
            SetupError.Text = "Локальный сеанс очищен. Выберите сервер и войдите снова.";
            ConnectButton.IsEnabled = true;
            StatusText.Text = "Требуется подключение";
        }
        catch
        {
            SetupError.Text = "Не удалось очистить локальный сеанс. Перезапустите PORTAL Desktop.";
            StatusText.Text = "Требуется перезапуск";
        }
    }

    private void ShowSetup(string? error = null)
    {
        Browser.Visibility = Visibility.Collapsed;
        SetupPanel.Visibility = Visibility.Visible;
        if (!string.IsNullOrWhiteSpace(_serverOrigin)) ServerUrlBox.Text = _serverOrigin;
        SetupError.Text = error ?? string.Empty;
        StatusText.Text = "Требуется подключение";
    }

    private async void Back_Click(object sender, RoutedEventArgs e)
    {
        if (Browser.Visibility != Visibility.Visible || Browser.CoreWebView2 is null) return;
        try
        {
            var handled = await Browser.ExecuteScriptAsync("Boolean(window.portalBack && window.portalBack())");
            if (string.Equals(handled, "true", StringComparison.OrdinalIgnoreCase)) return;
        }
        catch { }
        if (Browser.CanGoBack) Browser.GoBack();
    }

    private async void Home_Click(object sender, RoutedEventArgs e)
    {
        if (Browser.Visibility != Visibility.Visible || Browser.CoreWebView2 is null)
        {
            if (_serverOrigin is not null) await ConnectAsync(_serverOrigin, persist: false);
            return;
        }
        try
        {
            var handled = await Browser.ExecuteScriptAsync("Boolean(window.portalHome && window.portalHome())");
            if (string.Equals(handled, "true", StringComparison.OrdinalIgnoreCase)) return;
        }
        catch { }
        if (_serverOrigin is not null) Browser.Source = new Uri(_serverOrigin + "/web/");
    }

    private async void Browser_PreviewMouseWheel(object sender, MouseWheelEventArgs e)
    {
        if (Browser.Visibility != Visibility.Visible || Browser.CoreWebView2 is null) return;
        e.Handled = true;
        try
        {
            var delta = -Math.Sign(e.Delta) * Math.Max(80, Math.Abs(e.Delta));
            await Browser.ExecuteScriptAsync($"window.scrollBy({{top:{delta},left:0,behavior:'auto'}})");
        }
        catch { }
    }

    private void Reload_Click(object sender, RoutedEventArgs e)
    {
        if (Browser.Visibility == Visibility.Visible) Browser.Reload();
    }
    private async void CheckUpdate_Click(object sender, RoutedEventArgs e)
    {
        if (_serverOrigin is null)
        {
            MessageBox.Show("Сначала подключитесь к серверу PORTAL.", "PORTAL Desktop");
            return;
        }
        try
        {
            StatusText.Text = "Проверка версии…";
            var manifest = await LoadUpdateManifestAsync();
            if (manifest is null || manifest.Build <= CurrentBuild)
            {
                MessageBox.Show("Установлена актуальная версия PORTAL Desktop.", "PORTAL Desktop");
                return;
            }
            if (!ValidUpdateManifest(manifest, out var downloadUri))
                throw new InvalidDataException("Некорректный manifest обновления.");
            var answer = MessageBox.Show(
                $"Доступна версия {manifest.Version} (build {manifest.Build}). PORTAL сам скачает, проверит и установит обновление. Продолжить?",
                "Обновление PORTAL Desktop", MessageBoxButton.YesNo, MessageBoxImage.Information);
            if (answer == MessageBoxResult.Yes) await DownloadAndInstallUpdate(manifest, downloadUri);
        }
        catch
        {
            MessageBox.Show("Не удалось безопасно проверить обновление. Попробуйте позже.", "PORTAL Desktop");
        }
        finally
        {
            StatusText.Text = Browser.Visibility == Visibility.Visible ? "Подключено" : "Требуется подключение";
        }
    }
    private async Task<DesktopUpdateManifest?> LoadUpdateManifestAsync()
    {
        using var response = await Http.GetAsync(_serverOrigin + "/api/desktop-update");
        if (response.StatusCode != HttpStatusCode.NotFound)
        {
            response.EnsureSuccessStatusCode();
            return await JsonSerializer.DeserializeAsync<DesktopUpdateManifest>(
                await response.Content.ReadAsStreamAsync(),
                new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
                });
        }
        return await LoadGithubUpdateManifestAsync();
    }

    private static async Task<DesktopUpdateManifest?> LoadGithubUpdateManifestAsync()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get,
            $"https://api.github.com/repos/{GithubRepository}/releases?per_page=50");
        request.Headers.UserAgent.ParseAdd("PORTAL-Desktop/3.8.0");
        request.Headers.Accept.ParseAdd("application/vnd.github+json");
        using var response = await Http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();
        using var document = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync());
        if (document.RootElement.ValueKind != JsonValueKind.Array) return null;

        foreach (var release in document.RootElement.EnumerateArray())
        {
            if (release.TryGetProperty("draft", out var draft) && draft.GetBoolean()) continue;
            if (release.TryGetProperty("prerelease", out var prerelease) && prerelease.GetBoolean()) continue;
            if (!release.TryGetProperty("tag_name", out var tagNode)) continue;
            var tag = tagNode.GetString() ?? string.Empty;
            var match = Regex.Match(tag, @"^portal-desktop-v(\d+)\.(\d+)\.0$");
            if (!match.Success || !int.TryParse(match.Groups[1].Value, out var major) ||
                !int.TryParse(match.Groups[2].Value, out var minor) || minor is < 0 or > 9) continue;

            int build;
            try { build = checked(major * 10 + minor); }
            catch (OverflowException) { continue; }
            var version = $"{major}.{minor}.0";
            var expectedName = $"PORTAL-Desktop-win-x64-{version}.zip";
            if (!release.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array) continue;

            foreach (var asset in assets.EnumerateArray())
            {
                if (!asset.TryGetProperty("name", out var nameNode) || nameNode.GetString() != expectedName) continue;
                if (!asset.TryGetProperty("browser_download_url", out var urlNode) ||
                    !asset.TryGetProperty("digest", out var digestNode)) continue;
                var url = urlNode.GetString() ?? string.Empty;
                var digest = digestNode.GetString() ?? string.Empty;
                if (!digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)) continue;
                var sha256 = digest["sha256:".Length..];
                if (!Regex.IsMatch(sha256, "^[0-9a-fA-F]{64}$")) continue;
                return new DesktopUpdateManifest(build, version, url, sha256);
            }
        }
        return null;
    }

    private static bool ValidUpdateManifest(DesktopUpdateManifest manifest, out Uri downloadUri)
    {
        downloadUri = null!;
        if (manifest.Build <= 0 || !Regex.IsMatch(manifest.Version ?? string.Empty, @"^\d+\.\d+\.\d+$") ||
            !Regex.IsMatch(manifest.Sha256 ?? string.Empty, "^[0-9a-fA-F]{64}$") ||
            !Uri.TryCreate(manifest.DownloadUrl, UriKind.Absolute, out var uri)) return false;
        if (!string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) ||
            !uri.AbsolutePath.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)) return false;
        var secure = uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);
        var localHttp = uri.IsLoopback && uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase);
        if (!secure && !localHttp) return false;
        if (uri.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase))
        {
            var expectedPath = $"/{GithubRepository}/releases/download/portal-desktop-v{manifest.Version}/PORTAL-Desktop-win-x64-{manifest.Version}.zip";
            if (!uri.AbsolutePath.Equals(expectedPath, StringComparison.Ordinal)) return false;
        }
        downloadUri = uri;
        return true;
    }

    private static async Task<HttpResponseMessage> GetUpdateResponseAsync(Uri initial)
    {
        var current = initial;
        for (var redirects = 0; redirects <= 5; redirects++)
        {
            var response = await Http.GetAsync(current, HttpCompletionOption.ResponseHeadersRead);
            if ((int)response.StatusCode is >= 300 and < 400)
            {
                var location = response.Headers.Location;
                response.Dispose();
                if (location is null) throw new InvalidDataException("Обновление вернуло пустой redirect.");
                var next = location.IsAbsoluteUri ? location : new Uri(current, location);
                if (!AllowedUpdateRedirect(initial, next))
                    throw new InvalidDataException("Обновление перенаправлено на недоверенный адрес.");
                current = next;
                continue;
            }
            response.EnsureSuccessStatusCode();
            return response;
        }
        throw new InvalidDataException("Слишком много перенаправлений обновления.");
    }

    private static bool AllowedUpdateRedirect(Uri initial, Uri next)
    {
        var secure = next.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);
        var localHttp = next.IsLoopback && next.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase);
        if (!secure && !localHttp) return false;

        if (initial.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase))
        {
            return secure && (next.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase) ||
                next.Host.EndsWith(".githubusercontent.com", StringComparison.OrdinalIgnoreCase));
        }

        return next.GetLeftPart(UriPartial.Authority)
            .Equals(initial.GetLeftPart(UriPartial.Authority), StringComparison.OrdinalIgnoreCase);
    }

    private async Task DownloadAndInstallUpdate(DesktopUpdateManifest manifest, Uri downloadUri)
    {
        StatusText.Text = "Загрузка обновления…";
        using var response = await GetUpdateResponseAsync(downloadUri);
        if (response.Content.Headers.ContentLength is long length && length > MaxInstallerBytes)
            throw new InvalidDataException("Пакет обновления слишком большой.");

        var dir = Path.Combine(Path.GetTempPath(), "PORTAL");
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, $"PORTAL-Desktop-{manifest.Version}.zip");
        await using (var input = await response.Content.ReadAsStreamAsync())
        await using (var output = File.Create(file))
        {
            var buffer = new byte[81920];
            long total = 0;
            while (true)
            {
                var read = await input.ReadAsync(buffer);
                if (read == 0) break;
                total = checked(total + read);
                if (total > MaxInstallerBytes)
                {
                    output.Close();
                    File.Delete(file);
                    throw new InvalidDataException("Пакет обновления слишком большой.");
                }
                await output.WriteAsync(buffer.AsMemory(0, read));
            }
        }

        StatusText.Text = "Проверка обновления…";
        await using (var verify = File.OpenRead(file))
        {
            var actual = Convert.ToHexString(await SHA256.HashDataAsync(verify));
            if (!actual.Equals(manifest.Sha256, StringComparison.OrdinalIgnoreCase))
            {
                File.Delete(file);
                throw new InvalidDataException("SHA-256 пакета обновления не совпадает.");
            }
        }

        StatusText.Text = "Установка обновления…";
        var executable = InstallVerifiedPackage(file, manifest.Version);
        File.Delete(file);
        Process.Start(new ProcessStartInfo(executable) { UseShellExecute = true });
        Application.Current.Shutdown();
    }

    private static string InstallVerifiedPackage(string packagePath, string version)
    {
        const long maxExtractedBytes = 1024L * 1024 * 1024;
        var installRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PORTAL", "Desktop", "versions");
        var target = Path.Combine(installRoot, version);
        Directory.CreateDirectory(installRoot);

        if (!Directory.Exists(target))
        {
            var staging = Path.Combine(installRoot, ".staging-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(staging);
            try
            {
                using var archive = ZipFile.OpenRead(packagePath);
                if (archive.Entries.Count > 10000) throw new InvalidDataException("Слишком много файлов в обновлении.");
                var stagingRoot = Path.GetFullPath(staging).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                long extracted = 0;
                foreach (var entry in archive.Entries)
                {
                    if (string.IsNullOrWhiteSpace(entry.FullName) || entry.FullName.Contains('\\') ||
                        entry.FullName.StartsWith('/') || entry.FullName.Contains(':'))
                        throw new InvalidDataException("Небезопасный путь в пакете обновления.");

                    extracted = checked(extracted + entry.Length);
                    if (extracted > maxExtractedBytes) throw new InvalidDataException("Распакованное обновление слишком большое.");

                    var relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                    var destination = Path.GetFullPath(Path.Combine(staging, relative));
                    if (!destination.StartsWith(stagingRoot, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Путь обновления выходит за каталог установки.");

                    if (entry.FullName.EndsWith('/'))
                    {
                        Directory.CreateDirectory(destination);
                        continue;
                    }

                    Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                    using var input = entry.Open();
                    using var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
                    input.CopyTo(output);
                }

                var stagedExecutable = Path.Combine(staging, "PORTAL.Desktop.exe");
                if (!File.Exists(stagedExecutable))
                    throw new InvalidDataException("Пакет не содержит PORTAL.Desktop.exe.");
                Directory.Move(staging, target);
            }
            catch
            {
                if (Directory.Exists(staging)) Directory.Delete(staging, recursive: true);
                throw;
            }
        }

        var executable = Path.Combine(target, "PORTAL.Desktop.exe");
        if (!File.Exists(executable)) throw new InvalidDataException("Установленная версия PORTAL повреждена.");
        UpdateDesktopShortcuts(executable, target, version);
        return executable;
    }

    private static void UpdateDesktopShortcuts(string executable, string workingDirectory, string version)
    {
        var startMenu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "Microsoft", "Windows", "Start Menu", "Programs", "PORTAL", "PORTAL Desktop.lnk");
        WriteShortcut(startMenu, executable, workingDirectory, version);

        var desktop = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "PORTAL Desktop.lnk");
        WriteShortcut(desktop, executable, workingDirectory, version);
    }

    private static void WriteShortcut(string shortcutPath, string executable, string workingDirectory, string version)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(shortcutPath)!);
        var shellType = Type.GetTypeFromProgID("WScript.Shell")
            ?? throw new PlatformNotSupportedException("Не удалось создать ярлык PORTAL.");
        dynamic shell = Activator.CreateInstance(shellType)
            ?? throw new PlatformNotSupportedException("Не удалось создать ярлык PORTAL.");
        dynamic shortcut = shell.CreateShortcut(shortcutPath);
        shortcut.TargetPath = executable;
        shortcut.WorkingDirectory = workingDirectory;
        shortcut.Description = $"PORTAL Desktop {version}";
        shortcut.Save();
    }

    private sealed record DesktopSettings(string ServerOrigin);
    private sealed record DesktopUpdateManifest(int Build, string Version, string DownloadUrl, string Sha256);
}
