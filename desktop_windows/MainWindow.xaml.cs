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
    private const int CurrentBuild = 58;
    private const long MaxInstallerBytes = 250L * 1024 * 1024;
    private const string GithubRepository = "portal26ernest-arch/-Portal-zrp";
    private const string ServerDiscoveryUrl = "https://raw.githubusercontent.com/portal26ernest-arch/-Portal-zrp/main/portal-server.json";
    private const string PrimaryServerOrigin = "https://api.vart-portal.ru";
    private const string TrustedFallbackServerOrigin = "https://reserve-api.vart-portal.ru";
    private const string LegacyServerOrigin = "https://2a03-6f00-a--1-f426.sslip.io";
    private static readonly TimeSpan ServerProbeTimeout = TimeSpan.FromSeconds(5);
    private const string WebViewSoftwareRenderingArguments = "--disable-gpu --disable-gpu-compositing";
    private static readonly HttpClient Http = new(new HttpClientHandler { AllowAutoRedirect = false })
    {
        Timeout = TimeSpan.FromMinutes(5)
    };
    private readonly string _settingsDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PORTAL");
    private string? _serverOrigin;
    private bool _browserEventsAttached;
    private bool _webRecoveryPending;
    private string? _pendingPersistOrigin;
    private DesktopCacheBridge? _cacheBridge;
    private static MessengerWindow? _messengerWindow;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += MainWindow_Loaded;
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        var configured = Environment.GetEnvironmentVariable("PORTAL_SERVER_URL");
        if (!string.IsNullOrWhiteSpace(configured))
        {
            if (TryNormalizeOrigin(configured, out var configuredOrigin, out var configuredError))
            {
                ServerUrlBox.Text = configuredOrigin;
                await ConnectAsync(configuredOrigin, persist: false);
            }
            else
            {
                ShowSetup(configuredError);
            }
            return;
        }

        var preferred = LoadStoredOrigin();
        if (await ConnectFirstAvailablePortalServerAsync(preferred)) return;

        if (TryNormalizeOrigin(preferred, out var savedOrigin, out var savedError) && !IsAutomaticPortalOrigin(savedOrigin))
        {
            ServerUrlBox.Text = savedOrigin;
            await ConnectAsync(savedOrigin, persist: false);
            return;
        }

        ShowSetup("Не удалось найти доступный сервер PORTAL. Проверьте подключение к интернету.");
    }

    private static bool IsAutomaticPortalOrigin(string? raw)
    {
        if (!TryNormalizeOrigin(raw, out var origin, out _)) return false;
        return origin.Equals(PrimaryServerOrigin, StringComparison.OrdinalIgnoreCase) ||
               origin.Equals(TrustedFallbackServerOrigin, StringComparison.OrdinalIgnoreCase) ||
               origin.Equals(LegacyServerOrigin, StringComparison.OrdinalIgnoreCase);
    }

    private async Task<bool> ConnectFirstAvailablePortalServerAsync(string? preferred)
    {
        var candidates = new List<string>();
        void Add(string? raw)
        {
            if (!TryNormalizeOrigin(raw, out var normalized, out _)) return;
            if (!candidates.Contains(normalized, StringComparer.OrdinalIgnoreCase)) candidates.Add(normalized);
        }

        Add(preferred);
        var mayUsePortalFallback = string.IsNullOrWhiteSpace(preferred) || IsAutomaticPortalOrigin(preferred);
        if (mayUsePortalFallback)
        {
            Add(PrimaryServerOrigin);
            Add(TrustedFallbackServerOrigin);
            Add(LegacyServerOrigin);
        }

        foreach (var candidate in candidates)
        {
            StatusText.Text = candidate.Equals(TrustedFallbackServerOrigin, StringComparison.OrdinalIgnoreCase)
                ? "Подключаем резервный канал…"
                : "Проверяем сервер…";
            if (!await ProbePortalServerAsync(candidate)) continue;

            var previous = LoadStoredOrigin();
            var changed = !string.Equals(previous, candidate, StringComparison.OrdinalIgnoreCase);
            if (changed && !string.IsNullOrWhiteSpace(previous) && IsAutomaticPortalOrigin(previous) &&
                !DesktopCacheBridge.MigrateOutboxOrigin(_settingsDir, previous, candidate))
                continue;

            ServerUrlBox.Text = candidate;
            await ConnectAsync(candidate, persist: changed || string.IsNullOrWhiteSpace(previous));
            return true;
        }
        return false;
    }

    private static async Task<bool> ProbePortalServerAsync(string origin)
    {
        try
        {
            using var timeout = new CancellationTokenSource(ServerProbeTimeout);
            using var pingRequest = new HttpRequestMessage(HttpMethod.Get, origin + "/api/ping");
            pingRequest.Headers.Accept.ParseAdd("application/json");
            using var ping = await Http.SendAsync(pingRequest, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
            if (ping.StatusCode != HttpStatusCode.OK) return false;
            using var document = await JsonDocument.ParseAsync(await ping.Content.ReadAsStreamAsync(timeout.Token), cancellationToken: timeout.Token);
            if (!document.RootElement.TryGetProperty("ok", out var ok) || ok.ValueKind != JsonValueKind.True) return false;
            if (!document.RootElement.TryGetProperty("build", out var build) ||
                !(build.GetString() ?? string.Empty).StartsWith("PORTAL Server", StringComparison.Ordinal)) return false;

            using var webRequest = new HttpRequestMessage(HttpMethod.Get, origin + "/web/");
            using var web = await Http.SendAsync(webRequest, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
            return web.StatusCode == HttpStatusCode.OK;
        }
        catch
        {
            return false;
        }
    }

    private string WebViewArguments()
    {
        var forced = Environment.GetEnvironmentVariable("PORTAL_WEBVIEW_SOFTWARE_RENDERING");
        var marker = Path.Combine(_settingsDir, "software-rendering.flag");
        return string.Equals(forced, "1", StringComparison.Ordinal) || File.Exists(marker)
            ? WebViewSoftwareRenderingArguments
            : string.Empty;
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
            if (Browser.CoreWebView2 is null)
            {
                Directory.CreateDirectory(_settingsDir);
                var environmentOptions = new CoreWebView2EnvironmentOptions
                {
                    // GPU rendering is the fast default. On Windows/GPU driver combinations
                    // that show a blank WebView2 surface, software rendering remains an explicit
                    // compatibility fallback via environment flag or local marker.
                    AdditionalBrowserArguments = WebViewArguments()
                };
                var env = await CoreWebView2Environment.CreateAsync(
                    browserExecutableFolder: null,
                    userDataFolder: Path.Combine(_settingsDir, "WebView2"),
                    options: environmentOptions);
                var options = env.CreateCoreWebView2ControllerOptions();
                // Keep a normal per-user WebView profile so cookies/session state and any
                // cacheable web assets survive restarts. "Сменить сервер" still clears it explicitly.
                options.IsInPrivateModeEnabled = false;
                await Browser.EnsureCoreWebView2Async(env, options);
                await ConfigureBrowserAsync();
            }

            _serverOrigin = origin;
            ConfigureDesktopCache(origin);
            _pendingPersistOrigin = persist ? origin : null;
            SetupPanel.Visibility = Visibility.Collapsed;
            Browser.Visibility = Visibility.Visible;

            // Do not preflight /web/ with HttpClient. That used to add a full DNS/TCP/TLS
            // round trip before WebView2 could even begin loading the same page.
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

    private async Task ConfigureBrowserAsync()
    {
        if (Browser.CoreWebView2 is null) return;
        Browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
        Browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
        Browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
        // Use WebView2's built-in password manager. The credential is kept in the
        // per-user WebView2 profile, never serialized into PORTAL desktop.json.
        // WebView2 asks the user before saving/updating and can autofill it later.
        Browser.CoreWebView2.Settings.IsPasswordAutosaveEnabled = true;
        Browser.CoreWebView2.Settings.AreHostObjectsAllowed = true;
        var assemblyVersion = typeof(MainWindow).Assembly.GetName().Version;
        var versionName = assemblyVersion is null
            ? "0.0.0"
            : $"{assemblyVersion.Major}.{assemblyVersion.Minor}.{Math.Max(0, assemblyVersion.Build)}";
        var buildNumber = CurrentBuild.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var buildDate = string.Empty;
        foreach (var attribute in typeof(MainWindow).Assembly.GetCustomAttributes(typeof(System.Reflection.AssemblyMetadataAttribute), false))
        {
            if (attribute is not System.Reflection.AssemblyMetadataAttribute metadata) continue;
            if (metadata.Key == "PortalBuildNumber") buildNumber = metadata.Value ?? buildNumber;
            if (metadata.Key == "PortalBuildDate") buildDate = metadata.Value ?? string.Empty;
        }
        var buildMetadata = JsonSerializer.Serialize(new
        {
            applicationId = "ru.portal.desktop.windows",
            versionName,
            versionCode = CurrentBuild,
            buildNumber,
            buildDate,
            channel = "release",
            updatesConfigured = true,
            platform = "Windows Desktop"
        });
        var metadataLiteral = JsonSerializer.Serialize(buildMetadata);
        await Browser.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(
            "window.__PORTAL_BUILD_METADATA__=JSON.parse(" + metadataLiteral + ");window.__PORTAL_DESKTOP__=true;");
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
            if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var custom) && custom.Scheme == "portal-messenger")
            {
                var provider = custom.Query.Contains("provider=max", StringComparison.OrdinalIgnoreCase) ? "max" : "telegram";
                _ = OpenMessengerWindowAsync(provider);
                return;
            }
            if (_serverOrigin is not null && Uri.TryCreate(e.Uri, UriKind.Absolute, out var target))
            {
                if (SameOrigin(target, _serverOrigin)) Browser.Source = target;
                else OpenExternalHttps(target);
            }
        };
        Browser.CoreWebView2.NavigationCompleted += async (_, e) =>
        {
            if (_serverOrigin is null || Browser.Visibility != Visibility.Visible) return;
            BackButton.IsEnabled = true;
            _webRecoveryPending = false;

            if (!e.IsSuccess)
            {
                _pendingPersistOrigin = null;
                var failedOrigin = _serverOrigin;
                if (failedOrigin is not null &&
                    !failedOrigin.Equals(TrustedFallbackServerOrigin, StringComparison.OrdinalIgnoreCase) &&
                    IsAutomaticPortalOrigin(failedOrigin) &&
                    await ProbePortalServerAsync(TrustedFallbackServerOrigin))
                {
                    if (DesktopCacheBridge.MigrateOutboxOrigin(_settingsDir, failedOrigin, TrustedFallbackServerOrigin))
                    {
                        ServerUrlBox.Text = TrustedFallbackServerOrigin;
                        StatusText.Text = "Переключаемся на резервный канал…";
                        await ConnectAsync(TrustedFallbackServerOrigin, persist: true);
                        return;
                    }
                }
                ShowSetup($"Не удалось загрузить PORTAL ({e.WebErrorStatus}). Проверьте сеть и сервер.");
                return;
            }

            StatusText.Text = "Подключено";
            if (_pendingPersistOrigin is not null &&
                _pendingPersistOrigin.Equals(_serverOrigin, StringComparison.OrdinalIgnoreCase))
            {
                SaveOrigin(_pendingPersistOrigin);
                _pendingPersistOrigin = null;
            }
            await ApplyDesktopExperienceAsync();
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

    private async Task OpenMessengerWindowAsync(string provider = "telegram")
    {
        try
        {
            if (_messengerWindow is null) _messengerWindow = new MessengerWindow(_settingsDir);
            await _messengerWindow.OpenProviderAsync(provider);
            _messengerWindow.ShowSingleton();
        }
        catch { }
    }

    private async Task ApplyDesktopExperienceAsync()
    {
        if (Browser.CoreWebView2 is null) return;
        const string css = """
.web-client{--portal-blue:#0b5ed7;--portal-blue-dark:#0846a8;--portal-blue-soft:#eaf2ff;--accent:var(--portal-blue);--accent-soft:var(--portal-blue-soft);--bg:#f5f8fd;--soft:#edf3fb;--text:#172033;--muted:#66738a;--line:#dce5f2}
.web-client .top{background:var(--portal-blue)!important;border-bottom:0!important;color:#fff!important;box-shadow:0 8px 24px #0b4fbf22}
.web-client .top .portal-symbol{background:#fff!important;color:var(--portal-blue)!important}.web-client .top .wordmark{color:#fff!important}.web-client .top .company-name{color:#dceaff!important}
.web-client .hero,.web-client .today-main{background:linear-gradient(135deg,var(--portal-blue),var(--portal-blue-dark))!important}
@media(min-width:900px){
.web-client #app{min-height:100vh;padding-left:272px}.web-client .main{width:auto;max-width:none;margin:0;padding:34px 38px 54px}
.web-client .nav{position:fixed;inset:0 auto 0 0;width:272px;transform:none;z-index:35;display:flex;flex-direction:column;justify-content:flex-start;align-items:stretch;gap:4px;overflow-y:auto;background:linear-gradient(180deg,var(--portal-blue-dark),#063579);border:0;padding:22px 14px 18px;box-shadow:14px 0 36px #0b3b8017}
.web-client .nav::before{content:"PORTAL";display:block;color:#fff;font-size:25px;font-weight:850;letter-spacing:4px;padding:3px 12px 22px;border-bottom:1px solid #ffffff26;margin-bottom:10px}
.web-client .nav button{display:flex;flex-direction:row;align-items:center;justify-content:flex-start;gap:11px;flex:0 0 auto;max-width:none;width:100%;min-height:44px;padding:10px 12px;border-radius:11px;color:#dceaff;font-size:13px;text-align:left}
.web-client .nav button:hover{background:#ffffff12;color:#fff}.web-client .nav button.active{background:#fff;color:var(--portal-blue-dark);font-weight:750}
.web-client .nav .icon{width:19px;height:19px}.web-client .nav-group{display:grid;gap:3px;margin-top:10px}.web-client .nav-group-title{padding:8px 12px 4px;color:#9fc2f5;font-size:10px;font-weight:800;letter-spacing:1.1px;text-transform:uppercase}
.web-client .nav-spacer{flex:1;min-height:18px}.web-client .tiles{grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.web-client .sheet-backdrop{left:272px}
}
""";
        var cssJson = JsonSerializer.Serialize(css);
        var cssScript =
            "(() => {" +
            "if(!document.documentElement.classList.contains('web-client')) return false;globalThis.__PORTAL_DESKTOP__=true;document.documentElement.classList.add('desktop-client');" +
            "let style=document.getElementById('portal-desktop-43-style');" +
            "if(!style){style=document.createElement('style');style.id='portal-desktop-43-style';document.head.appendChild(style);}" +
            "style.textContent=" + cssJson + ";" +
            "return true;" +
            "})()";
        await Browser.ExecuteScriptAsync(cssScript);

        const string sidebarScript = """
(() => {
  if(!document.documentElement.classList.contains('web-client')) return false;
  if(window.__portalDesktop43Patched){ if(typeof buildNav==='function') buildNav(); return true; }
  if(typeof buildNav!=='function') return false;
  const original=buildNav, mq=matchMedia('(min-width:900px)');
  const navButton=(id,i,title)=>'<button data-action="go" data-page="'+id+'" class="'+(S.page===id?'active':'')+'" '+(S.page===id?'aria-current="page"':'')+'>'+icon(i)+'<span>'+esc(title)+'</span></button>';
  const desktopBuild=()=>{
    if(!mq.matches || typeof S==='undefined' || !S.me || typeof PortalCore==='undefined' || typeof can!=='function') return original();
    const nav=document.getElementById('nav'); if(!nav) return;
    if(typeof isOwner==='function' && isOwner() && !S.company){nav.innerHTML=navButton('companies','clients','Компании')+'<div class="nav-spacer"></div>'+navButton('settings','settings','Настройки');return;}
    const byId=Object.fromEntries(PortalCore.modules.map(m=>[m.id,m]));
    const groups=[['Работа',['organizer','work','jobs','batches','teamChat','messenger','notifications']],['Управление',['clients','users','permissions','tariffs']],['Учёт и финансы',['payroll','payrollPeriods','materials','invoices','expenses','documents','excelImport']],['Аналитика',['radar','analytics','reports','news']],['Система',['control','wms']]];
    let html=navButton('dashboard','home','Главная');
    for(const [title,ids] of groups){const allowed=ids.map(id=>byId[id]).filter(m=>m&&can(m.id));if(!allowed.length)continue;html+='<div class="nav-group"><div class="nav-group-title">'+esc(title)+'</div>'+allowed.map(m=>navButton(m.id,m.icon,m.title)).join('')+'</div>';}
    nav.innerHTML=html+'<div class="nav-spacer"></div>'+navButton('settings','settings','Настройки');
  };
  buildNav=desktopBuild; mq.addEventListener?.('change',desktopBuild); window.__portalDesktop43Patched=true; desktopBuild(); return true;
})()
""";
        await Browser.ExecuteScriptAsync(sidebarScript);
    }

    private void ConfigureDesktopCache(string origin)
    {
        if (Browser.CoreWebView2 is null) return;
        try { Browser.CoreWebView2.RemoveHostObjectFromScript("portalDesktopCache"); } catch { }
        _cacheBridge = new DesktopCacheBridge(_settingsDir, origin);
        Browser.CoreWebView2.AddHostObjectToScript("portalDesktopCache", _cacheBridge);
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
            _cacheBridge?.ClearAll();
            SetupError.Text = "Локальный сеанс и кэш компании очищены. Выберите сервер и войдите снова.";
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
        try
        {
            StatusText.Text = "Проверка сервера и версии…";
            var serverRefresh = await RefreshOfficialServerAsync();
            var manifest = await LoadUpdateManifestAsync();
            if (manifest is null || manifest.Build <= CurrentBuild)
            {
                var message = serverRefresh.Changed
                    ? "Адрес сервера PORTAL обновлён автоматически. Установлена актуальная версия PORTAL Desktop."
                    : serverRefresh.Checked
                        ? "Адрес сервера PORTAL проверен. Установлена актуальная версия PORTAL Desktop."
                        : "Установлена актуальная версия PORTAL Desktop. Адрес сервера проверить не удалось; сохранён текущий адрес.";
                MessageBox.Show(message, "PORTAL Desktop");
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
    private async Task<ServerRefreshResult> RefreshOfficialServerAsync()
    {
        try
        {
            if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("PORTAL_SERVER_URL")))
                return new ServerRefreshResult(false, false, _serverOrigin);

            using var request = new HttpRequestMessage(HttpMethod.Get, ServerDiscoveryUrl);
            request.Headers.UserAgent.ParseAdd("PORTAL-Desktop/5.8.0");
            request.Headers.Accept.ParseAdd("application/json");
            using var response = await Http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
            response.EnsureSuccessStatusCode();
            if (response.Content.Headers.ContentLength is > 16384)
                throw new InvalidDataException("Server discovery document is too large.");
            var bytes = await response.Content.ReadAsByteArrayAsync();
            if (bytes.Length == 0 || bytes.Length > 16384)
                throw new InvalidDataException("Server discovery document is invalid.");
            var document = JsonSerializer.Deserialize<ServerDiscoveryDocument>(bytes,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            if (document is null || document.SchemaVersion != 1 || document.Revision < 1 ||
                !DateTimeOffset.TryParse(document.UpdatedAt, out _) ||
                !TryNormalizeOfficialOrigin(document.ApiUrl, out var next))
                throw new InvalidDataException("Server discovery document is invalid.");

            var revisionPath = Path.Combine(_settingsDir, "server-discovery-revision.txt");
            var storedRevision = 0;
            if (File.Exists(revisionPath)) int.TryParse(File.ReadAllText(revisionPath).Trim(), out storedRevision);
            if (storedRevision > document.Revision)
                throw new InvalidDataException("Server discovery rollback rejected.");
            if (!await ProbeOfficialServerAsync(next))
            {
                var current = _serverOrigin ?? LoadStoredOrigin();
                if (IsAutomaticPortalOrigin(current) &&
                    await ProbePortalServerAsync(TrustedFallbackServerOrigin))
                {
                    var changedToFallback = !string.Equals(current, TrustedFallbackServerOrigin, StringComparison.OrdinalIgnoreCase);
                    if (changedToFallback && !string.IsNullOrWhiteSpace(current) &&
                        !DesktopCacheBridge.MigrateOutboxOrigin(_settingsDir, current, TrustedFallbackServerOrigin))
                        throw new IOException("Unable to migrate pending PORTAL work.");

                    if (changedToFallback)
                    {
                        ServerUrlBox.Text = TrustedFallbackServerOrigin;
                        await ConnectAsync(TrustedFallbackServerOrigin, persist: true);
                    }
                    return new ServerRefreshResult(false, changedToFallback, TrustedFallbackServerOrigin);
                }
                throw new InvalidDataException("Discovered PORTAL server is not ready.");
            }

            var previous = _serverOrigin ?? LoadStoredOrigin();
            var changed = !string.Equals(previous, next, StringComparison.OrdinalIgnoreCase);
            if (changed && !string.IsNullOrWhiteSpace(previous) &&
                !DesktopCacheBridge.MigrateOutboxOrigin(_settingsDir, previous, next))
                throw new IOException("Unable to migrate pending PORTAL work.");

            Directory.CreateDirectory(_settingsDir);
            File.WriteAllText(revisionPath, document.Revision.ToString());
            if (changed)
            {
                ServerUrlBox.Text = next;
                await ConnectAsync(next, persist: true);
            }
            else if (string.IsNullOrWhiteSpace(LoadStoredOrigin()))
            {
                SaveOrigin(next);
            }
            return new ServerRefreshResult(true, changed, next);
        }
        catch
        {
            return new ServerRefreshResult(false, false, _serverOrigin ?? LoadStoredOrigin());
        }
    }

    private static bool TryNormalizeOfficialOrigin(string? raw, out string origin)
    {
        origin = string.Empty;
        if (string.IsNullOrWhiteSpace(raw) || !Uri.TryCreate(raw.Trim(), UriKind.Absolute, out var uri) ||
            !uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) ||
            string.IsNullOrWhiteSpace(uri.Host) || !string.IsNullOrEmpty(uri.UserInfo) ||
            !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) ||
            (uri.Port != 443 && !uri.IsDefaultPort) || uri.AbsolutePath != "/" ||
            uri.IsLoopback || uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
            uri.Host.EndsWith(".localhost", StringComparison.OrdinalIgnoreCase) ||
            uri.Host.Equals("portal.invalid", StringComparison.OrdinalIgnoreCase) ||
            uri.Host.EndsWith(".trycloudflare.com", StringComparison.OrdinalIgnoreCase))
            return false;
        origin = uri.GetLeftPart(UriPartial.Authority).TrimEnd('/');
        return true;
    }

    private static Task<bool> ProbeOfficialServerAsync(string origin) => ProbePortalServerAsync(origin);

    private async Task<DesktopUpdateManifest?> LoadUpdateManifestAsync()
    {
        DesktopUpdateManifest? serverManifest = null;
        if (_serverOrigin is not null)
        {
            try
            {
                using var response = await Http.GetAsync(_serverOrigin + "/api/desktop-update");
                if (response.StatusCode != HttpStatusCode.NotFound)
                {
                    response.EnsureSuccessStatusCode();
                    serverManifest = await JsonSerializer.DeserializeAsync<DesktopUpdateManifest>(
                        await response.Content.ReadAsStreamAsync(),
                        new JsonSerializerOptions
                        {
                            PropertyNameCaseInsensitive = true,
                            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
                        });
                }
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
        }

        DesktopUpdateManifest? githubManifest = null;
        try { githubManifest = await LoadGithubUpdateManifestAsync(); }
        catch (HttpRequestException) { }
        catch (TaskCanceledException) { }

        if (githubManifest is not null && (serverManifest is null || githubManifest.Build > serverManifest.Build))
            return githubManifest;
        return serverManifest ?? githubManifest;
    }

    private static async Task<DesktopUpdateManifest?> LoadGithubUpdateManifestAsync()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get,
            $"https://api.github.com/repos/{GithubRepository}/releases?per_page=50");
        request.Headers.UserAgent.ParseAdd("PORTAL-Desktop/5.8.0");
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
            var expectedName = "portal-desktop-update.json";
            if (!release.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array) continue;

            foreach (var asset in assets.EnumerateArray())
            {
                if (!asset.TryGetProperty("name", out var nameNode) || nameNode.GetString() != expectedName ||
                    !asset.TryGetProperty("browser_download_url", out var urlNode)) continue;
                var manifestUri = urlNode.GetString();
                if (!Uri.TryCreate(manifestUri, UriKind.Absolute, out var parsedUri) ||
                    !parsedUri.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase)) continue;
                using var manifestResponse = await GetUpdateResponseAsync(parsedUri);
                manifestResponse.EnsureSuccessStatusCode();
                var manifest = await JsonSerializer.DeserializeAsync<DesktopUpdateManifest>(
                    await manifestResponse.Content.ReadAsStreamAsync(),
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true, PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower });
                if (manifest is not null && manifest.Build == build && manifest.Version == version &&
                    ValidUpdateManifest(manifest, out _)) return manifest;
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
        if (!DesktopUpdateSignature.Verify(manifest)) return false;
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
        if (!ValidUpdateManifest(manifest, out var verifiedUri) || verifiedUri != downloadUri)
            throw new InvalidDataException("Подпись manifest обновления не прошла проверку.");
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
    private sealed record ServerDiscoveryDocument(int SchemaVersion, int Revision, string ApiUrl, string UpdatedAt);
    private sealed record ServerRefreshResult(bool Checked, bool Changed, string? ServerUrl);
}
