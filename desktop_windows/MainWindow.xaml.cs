using Microsoft.Web.WebView2.Core;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;

namespace Portal.Desktop;

public partial class MainWindow : Window
{
    private const int CurrentBuild = 35;
    private const long MaxInstallerBytes = 250L * 1024 * 1024;
    private static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = false })
    {
        Timeout = TimeSpan.FromMinutes(5)
    };
    private readonly string _settingsDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PORTAL");
    private string? _serverOrigin;
    private bool _browserEventsAttached;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += MainWindow_Loaded;
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        var candidate = Environment.GetEnvironmentVariable("PORTAL_SERVER_URL") ?? LoadStoredOrigin();
        if (TryNormalizeOrigin(candidate, out var origin, out _))
        {
            ServerUrlBox.Text = origin;
            await ConnectAsync(origin, persist: false);
            return;
        }

        ShowSetup();
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
            StatusText.Text = "Подключение…";
            Directory.CreateDirectory(_settingsDir);
            var env = await CoreWebView2Environment.CreateAsync(
                userDataFolder: Path.Combine(_settingsDir, "WebView2"));
            await Browser.EnsureCoreWebView2Async(env);
            ConfigureBrowser();
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
        catch
        {
            ShowSetup("Не удалось открыть PORTAL. Проверьте адрес сервера и соединение.");
        }
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
            if (_serverOrigin is null || !Uri.TryCreate(e.Uri, UriKind.Absolute, out var target)) return;
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
            StatusText.Text = e.IsSuccess ? "Подключено" : "Ошибка подключения";
            BackButton.IsEnabled = Browser.CanGoBack;
        };
        Browser.CoreWebView2.ProcessFailed += (_, _) => StatusText.Text = "WebView остановлен — обновите страницу";
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

    private void Server_Click(object sender, RoutedEventArgs e) => ShowSetup();

    private void ShowSetup(string? error = null)
    {
        Browser.Visibility = Visibility.Collapsed;
        SetupPanel.Visibility = Visibility.Visible;
        if (!string.IsNullOrWhiteSpace(_serverOrigin)) ServerUrlBox.Text = _serverOrigin;
        SetupError.Text = error ?? string.Empty;
        StatusText.Text = "Требуется подключение";
    }

    private void Back_Click(object sender, RoutedEventArgs e)
    {
        if (Browser.CanGoBack) Browser.GoBack();
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
            using var response = await Http.GetAsync(_serverOrigin + "/api/desktop-update");
            if (response.StatusCode == HttpStatusCode.NotFound)
            {
                MessageBox.Show("Канал обновлений Desktop пока не настроен на этом сервере.", "PORTAL Desktop");
                return;
            }
            response.EnsureSuccessStatusCode();
            var manifest = await JsonSerializer.DeserializeAsync<DesktopUpdateManifest>(
                await response.Content.ReadAsStreamAsync(),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            if (manifest is null || manifest.Build <= CurrentBuild)
            {
                MessageBox.Show("Установлена актуальная версия PORTAL Desktop.", "PORTAL Desktop");
                return;
            }
            if (!ValidUpdateManifest(manifest, out var downloadUri))
                throw new InvalidDataException("Некорректный manifest обновления.");
            var answer = MessageBox.Show(
                $"Доступна версия {manifest.Version} (build {manifest.Build}). Скачать и запустить проверенный установщик?",
                "Обновление PORTAL Desktop", MessageBoxButton.YesNo, MessageBoxImage.Information);
            if (answer == MessageBoxResult.Yes) await DownloadAndLaunchUpdate(manifest, downloadUri);
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
    private static bool ValidUpdateManifest(DesktopUpdateManifest manifest, out Uri downloadUri)
    {
        downloadUri = null!;
        if (manifest.Build <= 0 || string.IsNullOrWhiteSpace(manifest.Version) ||
            !Regex.IsMatch(manifest.Sha256 ?? string.Empty, "^[0-9a-fA-F]{64}$") ||
            !Uri.TryCreate(manifest.DownloadUrl, UriKind.Absolute, out var uri)) return false;
        var secure = uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);
        var localHttp = uri.IsLoopback && uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase);
        if (!secure && !localHttp) return false;
        downloadUri = uri;
        return true;
    }

    private async Task DownloadAndLaunchUpdate(DesktopUpdateManifest manifest, Uri downloadUri)
    {
        StatusText.Text = "Загрузка обновления…";
        using var response = await Http.GetAsync(downloadUri, HttpCompletionOption.ResponseHeadersRead);
        response.EnsureSuccessStatusCode();
        if (response.Content.Headers.ContentLength is long length && length > MaxInstallerBytes)
            throw new InvalidDataException("Установщик слишком большой.");

        var dir = Path.Combine(Path.GetTempPath(), "PORTAL");
        Directory.CreateDirectory(dir);
        var file = Path.Combine(dir, "PORTAL_Desktop_Update_Setup.exe");
        await using (var input = await response.Content.ReadAsStreamAsync())
        await using (var output = File.Create(file))
        {
            await input.CopyToAsync(output);
            if (output.Length > MaxInstallerBytes) throw new InvalidDataException("Установщик слишком большой.");
        }
        await using var verify = File.OpenRead(file);
        var actual = Convert.ToHexString(await SHA256.HashDataAsync(verify));
        if (!actual.Equals(manifest.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            File.Delete(file);
            throw new InvalidDataException("SHA-256 установщика не совпадает.");
        }
        Process.Start(new ProcessStartInfo(file) { UseShellExecute = true });
        Application.Current.Shutdown();
    }

    private sealed record DesktopSettings(string ServerOrigin);
    private sealed record DesktopUpdateManifest(int Build, string Version, string DownloadUrl, string Sha256);
}
