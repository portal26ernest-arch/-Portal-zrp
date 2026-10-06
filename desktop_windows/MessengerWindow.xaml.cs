using Microsoft.Web.WebView2.Core;
using System.IO;
using System.Text.Json;
using System.Windows;

namespace Portal.Desktop;

internal sealed record MessengerRelayTicket(bool Enabled, string ProxyUrl, string UserName, string Password, string Realm)
{
    public static MessengerRelayTicket? Parse(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw) || raw.Length > 4096) return null;
        try
        {
            using var json = JsonDocument.Parse(raw);
            var root = json.RootElement;
            if (!root.TryGetProperty("enabled", out var enabled) || !enabled.GetBoolean()) return null;
            var proxy = root.GetProperty("proxy_url").GetString() ?? string.Empty;
            var user = root.GetProperty("username").GetString() ?? string.Empty;
            var password = root.GetProperty("password").GetString() ?? string.Empty;
            var realm = root.TryGetProperty("realm", out var realmNode) ? realmNode.GetString() ?? "PORTAL Messenger Relay" : "PORTAL Messenger Relay";
            if (!Uri.TryCreate(proxy, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps || string.IsNullOrWhiteSpace(uri.Host) ||
                !string.IsNullOrEmpty(uri.UserInfo) || (uri.Port != 443 && !uri.IsDefaultPort) && (uri.Port < 1 || uri.Port > 65535) ||
                (uri.AbsolutePath != "/" && uri.AbsolutePath != string.Empty) || user.Length is < 1 or > 256 || password.Length is < 1 or > 256 || realm.Length > 128)
                return null;
            return new MessengerRelayTicket(true, proxy.TrimEnd('/'), user, password, realm);
        }
        catch { return null; }
    }
}

public partial class MessengerWindow : Window
{
    private static readonly Uri TelegramUri = new("https://web.telegram.org/a/");
    private static readonly Uri MaxUri = new("https://web.max.ru/");
    private readonly string _settingsDir;
    private bool _closeRequested;
    private bool _initialized;
    private string _provider = "telegram";
    private MessengerRelayTicket? _relay;

    public MessengerWindow(string settingsDir, MessengerRelayTicket? relay = null)
    {
        InitializeComponent();
        _settingsDir = settingsDir;
        _relay = relay;
        RestoreWindowState();
        StateChanged += (_, _) => SaveWindowState();
        LocationChanged += (_, _) => SaveWindowState();
        SizeChanged += (_, _) => SaveWindowState();
        Loaded += async (_, _) => { await EnsureBrowserAsync(); await LoadProviderAsync(_provider); };
    }

    internal bool AcceptsRelay(MessengerRelayTicket? relay) =>
        (_relay is null && relay is null) || (_relay is not null && relay is not null &&
         _relay.ProxyUrl.Equals(relay.ProxyUrl, StringComparison.OrdinalIgnoreCase));

    internal void DisposeForRecreate()
    {
        _closeRequested = true;
        try { MessengerBrowser.Dispose(); } catch { }
        Close();
    }

    public async Task OpenProviderAsync(string? provider, MessengerRelayTicket? relay = null)
    {
        _provider = NormalizeProvider(provider);
        if (relay is not null) _relay = relay;
        await EnsureBrowserAsync();
        await LoadProviderAsync(_provider);
    }

    public void ShowSingleton()
    {
        if (!IsVisible) Show();
        if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal;
        Activate();
    }

    internal static bool IsAllowedProviderUri(Uri? uri)
    {
        if (uri is null || uri.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(uri.UserInfo) || (uri.Port != 443 && !uri.IsDefaultPort)) return false;
        return uri.Host.Equals("web.telegram.org", StringComparison.OrdinalIgnoreCase) ||
               uri.Host.Equals("web.max.ru", StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizeProvider(string? value) => value?.Equals("max", StringComparison.OrdinalIgnoreCase) == true ? "max" : "telegram";
    private static Uri ProviderUri(string provider) => provider == "max" ? MaxUri : TelegramUri;

    private async Task EnsureBrowserAsync()
    {
        if (_initialized) return;
        var profile = Path.Combine(_settingsDir, "MessengerWebView2");
        Directory.CreateDirectory(profile);
        CoreWebView2EnvironmentOptions? options = null;
        if (_relay is not null)
            options = new CoreWebView2EnvironmentOptions($"--proxy-server={_relay.ProxyUrl}");
        var environment = await CoreWebView2Environment.CreateAsync(null, profile, options);
        await MessengerBrowser.EnsureCoreWebView2Async(environment);
        MessengerBrowser.CoreWebView2.Settings.AreDevToolsEnabled = false;
        MessengerBrowser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        MessengerBrowser.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
        MessengerBrowser.CoreWebView2.NavigationStarting += (_, e) =>
        {
            if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) || !IsAllowedProviderUri(target)) e.Cancel = true;
        };
        MessengerBrowser.CoreWebView2.BasicAuthenticationRequested += (_, e) =>
        {
            var relay = _relay;
            if (relay is null || string.IsNullOrWhiteSpace(e.Challenge) || !e.Challenge.Contains(relay.Realm, StringComparison.Ordinal))
            {
                e.Cancel = true;
                return;
            }
            e.Response.UserName = relay.UserName;
            e.Response.Password = relay.Password;
        };
        MessengerBrowser.CoreWebView2.NavigationCompleted += (_, e) =>
        {
            RelayStatus.Text = e.IsSuccess
                ? (_relay is null ? "Канал: прямой" : "Канал: PORTAL Relay")
                : (_relay is null ? $"Прямой канал: {e.WebErrorStatus}" : $"PORTAL Relay: {e.WebErrorStatus}");
        };
        RelayStatus.Text = _relay is null ? "Канал: прямой" : "Канал: PORTAL Relay";
        _initialized = true;
    }

    private async Task LoadProviderAsync(string provider)
    {
        _provider = NormalizeProvider(provider);
        TelegramTab.IsEnabled = _provider != "telegram";
        MaxTab.IsEnabled = _provider != "max";
        var target = ProviderUri(_provider);
        if (MessengerBrowser.Source is null || !MessengerBrowser.Source.AbsoluteUri.Equals(target.AbsoluteUri, StringComparison.OrdinalIgnoreCase))
            MessengerBrowser.Source = target;
        await Task.CompletedTask;
    }

    private async void TelegramTab_Click(object sender, RoutedEventArgs e) => await LoadProviderAsync("telegram");
    private async void MaxTab_Click(object sender, RoutedEventArgs e) => await LoadProviderAsync("max");

    private string StatePath => Path.Combine(_settingsDir, "messenger-window.json");
    private void RestoreWindowState()
    {
        try
        {
            if (!File.Exists(StatePath)) return;
            var state = JsonSerializer.Deserialize<MessengerWindowState>(File.ReadAllText(StatePath));
            if (state is null) return;
            Width = Math.Clamp(state.Width, MinWidth, 1200); Height = Math.Clamp(state.Height, MinHeight, 1200);
            Left = state.Left; Top = state.Top;
            WindowState = state.WindowState == "Maximized" ? WindowState.Maximized : WindowState.Normal;
        }
        catch { }
    }

    private void SaveWindowState()
    {
        try
        {
            Directory.CreateDirectory(_settingsDir);
            var bounds = RestoreBounds;
            var state = new MessengerWindowState(bounds.Left, bounds.Top, bounds.Width, bounds.Height, WindowState.ToString());
            File.WriteAllText(StatePath, JsonSerializer.Serialize(state));
        }
        catch { }
    }

    private void MessengerWindow_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        if (_closeRequested) return;
        e.Cancel = true;
        Hide();
    }

    private sealed record MessengerWindowState(double Left, double Top, double Width, double Height, string WindowState);
}
