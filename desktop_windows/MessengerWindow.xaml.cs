using Microsoft.Web.WebView2.Core;
using System.IO;
using System.Text.Json;
using System.Windows;

namespace Portal.Desktop;

public partial class MessengerWindow : Window
{
    private readonly string _settingsDir;
    private bool _closeRequested;
    private bool _initialized;

    public MessengerWindow(string settingsDir)
    {
        InitializeComponent();
        _settingsDir = settingsDir;
        RestoreWindowState();
        StateChanged += (_, _) => SaveWindowState();
        LocationChanged += (_, _) => SaveWindowState();
        SizeChanged += (_, _) => SaveWindowState();
        Loaded += async (_, _) => await EnsureBrowserAsync();
    }

    public async Task LoadSessionAsync(string origin, string token, int? companyId, string? companyJson)
    {
        if (!Uri.TryCreate(origin, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps && !uri.IsLoopback)
            throw new InvalidOperationException("Messenger requires the configured PORTAL server origin");
        if (token.Length is < 16 or > 8192) throw new InvalidOperationException("Invalid authenticated session");
        await EnsureBrowserAsync();
        var session = JsonSerializer.Serialize(new { server = origin, token });
        var company = companyJson ?? "null";
        var script = "window.__PORTAL_DESKTOP__=true;window.__PORTAL_MESSENGER_COMPANY__=" + company + ";" +
                     "sessionStorage.setItem('portalSession'," + JsonSerializer.Serialize(session) + ");";
        await MessengerBrowser.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(script);
        await MessengerBrowser.CoreWebView2.ExecuteScriptAsync(script);
        MessengerBrowser.Source = new Uri(origin.TrimEnd('/') + "/web/");
    }

    public void ShowSingleton()
    {
        if (!IsVisible) Show();
        if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal;
        Activate();
    }

    private async Task EnsureBrowserAsync()
    {
        if (_initialized) return;
        Directory.CreateDirectory(Path.Combine(_settingsDir, "MessengerWebView2"));
        var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: Path.Combine(_settingsDir, "MessengerWebView2"));
        await MessengerBrowser.EnsureCoreWebView2Async(environment);
        MessengerBrowser.CoreWebView2.Settings.AreDevToolsEnabled = false;
        MessengerBrowser.CoreWebView2.NewWindowRequested += (_, e) => e.Handled = true;
        MessengerBrowser.CoreWebView2.NavigationStarting += (_, e) =>
        {
            if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target) || target.Scheme != Uri.UriSchemeHttps && !target.IsLoopback)
                e.Cancel = true;
        };
        _initialized = true;
    }

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
            var bounds = WindowState == WindowState.Normal ? RestoreBounds : RestoreBounds;
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
