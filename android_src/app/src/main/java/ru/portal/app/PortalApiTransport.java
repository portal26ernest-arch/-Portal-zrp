package ru.portal.app;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;
import java.util.function.Predicate;

import okhttp3.Call;
import okhttp3.Dns;
import okhttp3.HttpUrl;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.dnsoverhttps.DnsOverHttps;

/** App-only recovery for unreachable system-DNS routes. Never changes Android DNS. */
final class PortalApiTransport {
    static final long RECOVERY_TTL_MS = 120_000L;
    private final Call.Factory directRequests;
    private final Call.Factory recoveryRequests;
    private final Call.Factory directProbes;
    private final Call.Factory recoveryProbes;
    private final LongSupplier clock;
    private final ConcurrentHashMap<String, Long> recoveredUntil = new ConcurrentHashMap<>();

    PortalApiTransport() {
        OkHttpClient direct = apiClient();
        OkHttpClient recovered = direct.newBuilder().dns(officialDns(encryptedDns())).build();
        directRequests = direct;
        recoveryRequests = recovered;
        directProbes = direct.newBuilder().callTimeout(5500, TimeUnit.MILLISECONDS).build();
        recoveryProbes = recovered.newBuilder().callTimeout(7500, TimeUnit.MILLISECONDS).build();
        clock = System::currentTimeMillis;
    }

    // Injectable transports keep the recovery/POST/expiry tests independent of live DNS.
    PortalApiTransport(Call.Factory direct, Call.Factory recovered, LongSupplier clock) {
        directRequests = directProbes = direct;
        recoveryRequests = recoveryProbes = recovered;
        this.clock = clock;
    }

    static OkHttpClient apiClient() {
        return new OkHttpClient.Builder()
                .connectTimeout(5000, TimeUnit.MILLISECONDS)
                .readTimeout(10000, TimeUnit.MILLISECONDS)
                .callTimeout(15000, TimeUnit.MILLISECONDS)
                .followRedirects(false).followSslRedirects(false)
                // A server can commit a POST before the connection fails. Do not replay it.
                .retryOnConnectionFailure(false).build();
    }

    private static Dns encryptedDns() {
        try {
            OkHttpClient resolverClient = apiClient().newBuilder()
                    .callTimeout(4000, TimeUnit.MILLISECONDS).build();
            return new DnsOverHttps.Builder().client(resolverClient)
                    .url(HttpUrl.get("https://cloudflare-dns.com/dns-query"))
                    .bootstrapDnsHosts(InetAddress.getByAddress(new byte[]{1, 1, 1, 1}),
                            InetAddress.getByAddress(new byte[]{1, 0, 0, 1}))
                    .includeIPv6(false).resolvePrivateAddresses(false).post(true).build();
        } catch (UnknownHostException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    static boolean officialHost(String host) {
        return "api.vart-portal.ru".equalsIgnoreCase(host)
                || "reserve-api.vart-portal.ru".equalsIgnoreCase(host);
    }

    static Dns officialDns(Dns resolver) {
        return host -> {
            if (!officialHost(host)) throw new UnknownHostException("Recovery is restricted to PORTAL");
            List<InetAddress> addresses = new ArrayList<>();
            for (InetAddress address : resolver.lookup(host)) {
                byte[] bytes = address.getAddress();
                int a = bytes[0] & 255;
                int b = bytes[1] & 255;
                if (bytes.length == 4 && !address.isAnyLocalAddress() && !address.isLoopbackAddress()
                        && !address.isLinkLocalAddress() && !address.isSiteLocalAddress()
                        && !address.isMulticastAddress() && a < 224
                        && !(a == 100 && b >= 64 && b <= 127)
                        && !(a == 198 && (b == 18 || b == 19))) addresses.add(address);
            }
            if (addresses.isEmpty()) throw new UnknownHostException("No public PORTAL addresses");
            return addresses;
        };
    }

    private boolean eligible(HttpUrl url) {
        return url.isHttps() && url.port() == 443 && officialHost(url.host())
                && url.username().isEmpty() && url.password().isEmpty();
    }

    boolean recoveryActive(HttpUrl url) {
        return eligible(url) && recoveredUntil.getOrDefault(url.host(), 0L) > clock.getAsLong();
    }

    boolean probe(String base, Predicate<String> validPortalPing) {
        HttpUrl url = HttpUrl.parse(base + "/api/ping");
        if (url == null || !eligible(url)) return false;
        Request request = new Request.Builder().url(url).header("Accept", "application/json").get().build();
        if (recoveryActive(url)) {
            if (validProbe(recoveryProbes, request, validPortalPing)) return true;
            recoveredUntil.remove(url.host());
        }
        if (validProbe(directProbes, request, validPortalPing)) return true;
        if (!validProbe(recoveryProbes, request, validPortalPing)) return false;
        // Activation requires an anonymous, TLS-verified PORTAL health response.
        recoveredUntil.put(url.host(), clock.getAsLong() + RECOVERY_TTL_MS);
        return true;
    }

    private boolean validProbe(Call.Factory factory, Request request, Predicate<String> valid) {
        try {
            Payload payload = read(factory, request, 32768);
            return payload.status == 200 && valid.test(payload.body);
        } catch (Exception failure) { return false; }
    }

    Payload execute(Request request, int limit) throws IOException {
        // Exactly one execution, also for POST. Failover belongs to the caller's safe-GET policy.
        return read(recoveryActive(request.url()) ? recoveryRequests : directRequests, request, limit);
    }

    private static Payload read(Call.Factory factory, Request request, int limit) throws IOException {
        try (Response response = factory.newCall(request).execute()) {
            if (response.body() == null) return new Payload(response.code(), "");
            if (response.body().contentLength() > limit) throw new IOException("Response too large");
            try (InputStream input = response.body().byteStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[4096];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (output.size() + count > limit) throw new IOException("Response too large");
                    output.write(buffer, 0, count);
                }
                return new Payload(response.code(), output.toString(StandardCharsets.UTF_8.name()));
            }
        }
    }

    static final class Payload {
        final int status;
        final String body;
        Payload(int status, String body) { this.status = status; this.body = body; }
    }
}
