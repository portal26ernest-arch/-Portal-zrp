using Microsoft.Web.WebView2.Core;
using System.IO;
using System.Text.Json;
using System.Globalization;
using System.Windows;

namespace Portal.Desktop;

public sealed record MessengerRelayTicket(bool Enabled, bool Required, string ProxyUrl, string WssUrl, string UserName, string Password, string Realm)
{
    private static MessengerRelayTicket FailClosed => new(false, true, string.Empty, string.Empty, string.Empty, string.Empty, "PORTAL Messenger Relay");
    public bool HasDirectTransport => Enabled && !string.IsNullOrWhiteSpace(ProxyUrl);
    public bool HasWssTransport => Enabled && !string.IsNullOrWhiteSpace(WssUrl);

    public static MessengerRelayTicket? Parse(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw) || raw.Length > 4096) return FailClosed;
        try
        {
            using var json = JsonDocument.Parse(raw);
            var root = json.RootElement;
            if (!root.TryGetProperty("provider", out var provider) || provider.GetString() != "telegram") return FailClosed;
            if (!root.TryGetProperty("enabled", out var enabled) || !root.TryGetProperty("required", out var requiredNode) ||
                enabled.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                requiredNode.ValueKind is not (JsonValueKind.True or JsonValueKind.False)) return FailClosed;
            var isEnabled = enabled.GetBoolean();
            var required = requiredNode.GetBoolean();
            var proxy = isEnabled && root.TryGetProperty("proxy_url", out var proxyNode) ? proxyNode.GetString() ?? string.Empty : string.Empty;
            var wss = isEnabled && root.TryGetProperty("wss_url", out var wssNode) ? wssNode.GetString() ?? string.Empty : string.Empty;
            var user = isEnabled ? root.GetProperty("username").GetString() ?? string.Empty : string.Empty;
            var password = isEnabled ? root.GetProperty("password").GetString() ?? string.Empty : string.Empty;
            var realm = root.TryGetProperty("realm", out var realmNode) ? realmNode.GetString() ?? "PORTAL Messenger Relay" : "PORTAL Messenger Relay";
            if (isEnabled)
            {
                if (string.IsNullOrWhiteSpace(proxy) && string.IsNullOrWhiteSpace(wss)) return FailClosed;
                if (!string.IsNullOrWhiteSpace(proxy) && (!Uri.TryCreate(proxy, UriKind.Absolute, out var proxyUri) ||
                    proxyUri.Scheme != Uri.UriSchemeHttps || string.IsNullOrWhiteSpace(proxyUri.Host) ||
                    !string.IsNullOrEmpty(proxyUri.UserInfo) || ((proxyUri.Port != 443 && !proxyUri.IsDefaultPort) && (proxyUri.Port < 1 || proxyUri.Port > 65535)) ||
                    (proxyUri.AbsolutePath != "/" && proxyUri.AbsolutePath != string.Empty) || !string.IsNullOrEmpty(proxyUri.Query) || !string.IsNullOrEmpty(proxyUri.Fragment)))
                    return FailClosed;
                if (!string.IsNullOrWhiteSpace(wss) && (!Uri.TryCreate(wss, UriKind.Absolute, out var wssUri) ||
                    wssUri.Scheme != "wss" || string.IsNullOrWhiteSpace(wssUri.Host) || !string.IsNullOrEmpty(wssUri.UserInfo) ||
                    wssUri.Port != 443 || wssUri.AbsolutePath != "/connect" || !string.IsNullOrEmpty(wssUri.Query) || !string.IsNullOrEmpty(wssUri.Fragment)))
                    return FailClosed;
                if (user.Length is < 1 or > 256 || password.Length is < 1 or > 256 || realm.Length > 128 ||
                    !root.TryGetProperty("expires_at", out var expires) ||
                    !DateTimeOffset.TryParse(expires.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var expiry) ||
                    expiry <= DateTimeOffset.UtcNow)
                    return FailClosed;
            }
            return new MessengerRelayTicket(isEnabled, required, proxy.TrimEnd('/'), wss, user, password, realm);
        }
        catch { return FailClosed; }
    }
}

public partial class MessengerWindow : Window
{
    private static readonly Uri TelegramUri = new("https://web.telegram.org/a/");
    private static readonly Uri MaxUri = new("https://web.max.ru/");
    private readonly string _settingsDir;
    private const string TelegramProfileName = "MessengerWebView2-Telegram";
    private const string MaxProfileName = "MessengerWebView2-Max";
    private bool _closeRequested;
    private bool _initialized;
    private bool _telegramInitialized;
    private string _provider = "telegram";
    private MessengerRelayTicket? _relay;
    private MessengerWssLocalProxy? _wssLocalProxy;

    public MessengerWindow(string settingsDir, MessengerRelayTicket? relay = null)
    {
        InitializeComponent();
        _settingsDir = settingsDir;
        _relay = relay;
        RestoreWindowState();
        StateChanged += (_, _) => SaveWindowState();
        LocationChanged += (_, _) => SaveWindowState();
        SizeChanged += (_, _) => SaveWindowState();
    }

    internal bool AcceptsRelay(MessengerRelayTicket? relay) =>
        (_relay is null && relay is null) || (_relay is not null && relay is not null &&
         _relay.ProxyUrl.Equals(relay.ProxyUrl, StringComparison.OrdinalIgnoreCase) &&
         _relay.WssUrl.Equals(relay.WssUrl, StringComparison.OrdinalIgnoreCase) &&
         (!_relay.HasWssTransport || (_relay.UserName == relay.UserName && _relay.Password == relay.Password)));

    private void DisposeWssLocalProxy()
    {
        try { _wssLocalProxy?.Dispose(); } catch { }
        _wssLocalProxy = null;
    }

    internal void DisposeForRecreate()
    {
        _closeRequested = true;
        DisposeWssLocalProxy();
        try { TelegramWebView2.Dispose(); MaxWebView2.Dispose(); } catch { }
        Close();
    }

    private void DeleteProfileDirectory(string profileName)
    {
        try
        {
            var root = Path.GetFullPath(_settingsDir);
            var profile = Path.GetFullPath(Path.Combine(root, profileName));
            if (profile.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) && Directory.Exists(profile))
                Directory.Delete(profile, recursive: true);
        }
        catch { }
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

    internal void CloseForIdentityChange()
    {
        _closeRequested = true;
        DisposeWssLocalProxy();
        Close();
    }

    internal async Task ClearAndCloseAsync()
    {
        try { if (TelegramWebView2.CoreWebView2 is not null) await TelegramWebView2.CoreWebView2.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.AllProfile); } catch { }
        try { if (MaxWebView2.CoreWebView2 is not null) await MaxWebView2.CoreWebView2.Profile.ClearBrowsingDataAsync(CoreWebView2BrowsingDataKinds.AllProfile); } catch { }
        _closeRequested = true;
        DisposeWssLocalProxy();
        try { TelegramWebView2.Dispose(); MaxWebView2.Dispose(); } catch { }
        DeleteProfileDirectory(TelegramProfileName);
        DeleteProfileDirectory(MaxProfileName);
        Close();
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
        await InitializeViewAsync(MaxWebView2, MaxProfileName, null, false);
        if (_relay?.Required != true || _relay.Enabled == true) await InitializeTelegramAsync();
        _initialized = true;
    }

    private async Task<bool> InitializeTelegramAsync()
    {
        if (_telegramInitialized) return true;
        CoreWebView2EnvironmentOptions? options = null;
        if (_relay?.Enabled == true)
        {
            if (_relay.HasWssTransport)
            {
                try
                {
                    DisposeWssLocalProxy();
                    _wssLocalProxy = MessengerWssLocalProxy.Start(_relay);
                    options = new CoreWebView2EnvironmentOptions($"--proxy-server={_wssLocalProxy.ProxyUrl}");
                }
                catch
                {
                    DisposeWssLocalProxy();
                    if (_relay.HasDirectTransport)
                        options = new CoreWebView2EnvironmentOptions($"--proxy-server={_relay.ProxyUrl}");
                    else
                    {
                        RelayStatus.Text = "Защищённый канал PORTAL временно недоступен.";
                        return false;
                    }
                }
            }
            else if (_relay.HasDirectTransport)
            {
                options = new CoreWebView2EnvironmentOptions($"--proxy-server={_relay.ProxyUrl}");
            }
            else
            {
                RelayStatus.Text = "Защищённый канал PORTAL временно недоступен.";
                return false;
            }
        }
        await InitializeViewAsync(TelegramWebView2, TelegramProfileName, options, true);
        _telegramInitialized = true;
        return true;
    }

    private async Task InitializeViewAsync(Microsoft.Web.WebView2.Wpf.WebView2 view, string profileName, CoreWebView2EnvironmentOptions? options, bool telegram)
    {
        var profile = Path.Combine(_settingsDir, profileName);
        Directory.CreateDirectory(profile);
        var environment = await CoreWebView2Environment.CreateAsync(null, profile, options);
        await view.EnsureCoreWebView2Async(environment);
        view.CoreWebView2.Settings.AreDevToolsEnabled = false;
        view.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        view.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
        view.CoreWebView2.NavigationStarting += (_, e) =>
        {
            if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) || !IsAllowedProviderUri(target)) e.Cancel = true;
        };
        if (telegram) view.CoreWebView2.BasicAuthenticationRequested += (_, e) =>
        {
            var relay = _relay;
            if (_wssLocalProxy is not null || relay?.HasDirectTransport != true ||
                string.IsNullOrWhiteSpace(e.Challenge) || !e.Challenge.Contains(relay.Realm, StringComparison.Ordinal))
            {
                e.Cancel = true;
                return;
            }
            e.Response.UserName = relay.UserName;
            e.Response.Password = relay.Password;
        };
        view.CoreWebView2.NavigationCompleted += (_, e) =>
        {
            if (_provider != (telegram ? "telegram" : "max")) return;
            RelayStatus.Text = e.IsSuccess ? (telegram && _relay?.Enabled == true ? "Telegram: защищённый канал PORTAL" : telegram ? "Telegram: прямое подключение" : "MAX: прямое подключение") : $"Не удалось загрузить: {e.WebErrorStatus}";
        };
    }

    private async Task LoadProviderAsync(string provider)
    {
        _provider = NormalizeProvider(provider);
        TelegramTab.IsEnabled = _provider != "telegram";
        MaxTab.IsEnabled = _provider != "max";
        var target = ProviderUri(_provider);
        if (_provider == "telegram" && _relay?.Required == true && _relay.Enabled != true)
        {
            RelayStatus.Text = "Telegram доступен только через защищённый канал PORTAL; канал пока недоступен.";
            TelegramWebView2.Visibility = Visibility.Visible; MaxWebView2.Visibility = Visibility.Collapsed;
            TelegramWebView2.Source = new Uri("about:blank");
            return;
        }
        if (_provider == "telegram" && !_telegramInitialized && !await InitializeTelegramAsync())
        {
            TelegramWebView2.Visibility = Visibility.Visible;
            MaxWebView2.Visibility = Visibility.Collapsed;
            return;
        }
        var browser = _provider == "telegram" ? TelegramWebView2 : MaxWebView2;
        browser.Visibility = Visibility.Visible;
        (_provider == "telegram" ? MaxWebView2 : TelegramWebView2).Visibility = Visibility.Collapsed;
        RelayStatus.Text = _provider == "telegram" && _relay?.Enabled == true
            ? "Telegram: защищённый канал PORTAL" : "MAX: прямое подключение";
        if (browser.Source is null || !browser.Source.AbsoluteUri.Equals(target.AbsoluteUri, StringComparison.OrdinalIgnoreCase)) browser.Source = target;
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
