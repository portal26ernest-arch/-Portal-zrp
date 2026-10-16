package ru.portal.app;

import static org.junit.Assert.*;
import org.junit.Test;
import java.io.IOException;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.net.ssl.SSLHandshakeException;
import okhttp3.*;
import okio.Timeout;

public class PortalApiTransportTest {
    private static final String BASE = "https://api.vart-portal.ru";
    private static final String PING = "{\"ok\":true,\"build\":\"PORTAL Server 4.8\"}";

    @Test public void healthySystemRouteDoesNotUseAlternateDnsOrCredentialsForProbe() {
        Scripted direct = new Scripted(new Reply(200, PING));
        Scripted recovery = new Scripted();
        PortalApiTransport transport = new PortalApiTransport(direct, recovery, () -> 10L);
        assertTrue(transport.probe(BASE, PING::equals));
        assertEquals(0, recovery.requests.size());
        Request probe = direct.requests.get(0);
        assertEquals("GET", probe.method());
        assertEquals(BASE + "/api/ping", probe.url().toString());
        assertNull(probe.header("Authorization"));
        assertNull(probe.header("X-Portal-Company"));
        assertFalse(transport.recoveryActive(probe.url()));
    }

    @Test public void failedSystemDnsRecoversBeforeFirstPostAndKeepsHttpsHostname() throws Exception {
        Scripted direct = new Scripted(new UnknownHostException("system resolver"));
        Scripted recovery = new Scripted(new Reply(200, PING), new Reply(200, "{\"ok\":true}"));
        PortalApiTransport transport = new PortalApiTransport(direct, recovery, () -> 10L);
        assertTrue(transport.probe(BASE, PING::equals));
        Request post = new Request.Builder().url(BASE + "/api/login")
                .header("Authorization", "Bearer test-only-token")
                .header("X-Portal-Company", "1")
                .post(RequestBody.create("{}", MediaType.get("application/json"))).build();
        assertEquals(200, transport.execute(post, 100).status);
        assertEquals(1, direct.requests.size()); // anonymous probe only
        assertEquals(2, recovery.requests.size());
        assertNull(recovery.requests.get(0).header("Authorization"));
        assertSame(post, recovery.requests.get(1));
        assertEquals("api.vart-portal.ru", recovery.requests.get(1).url().host());
        assertTrue(recovery.requests.get(1).url().isHttps());
    }

    @Test public void nonPortalHealthBodyNeverActivatesRecovery() {
        Scripted direct = new Scripted(new IOException("unreachable"));
        Scripted recovery = new Scripted(new Reply(200, "<html>Not PORTAL</html>"));
        PortalApiTransport transport = new PortalApiTransport(direct, recovery, () -> 10L);
        assertFalse(transport.probe(BASE, PING::equals));
        assertFalse(transport.recoveryActive(HttpUrl.get(BASE)));
    }

    @Test public void unauthorizedHealthNeverActivatesRecovery() {
        PortalApiTransport transport = new PortalApiTransport(
                new Scripted(new IOException("unreachable")),
                new Scripted(new Reply(401, PING)), () -> 10L);
        assertFalse(transport.probe(BASE, PING::equals));
        assertFalse(transport.recoveryActive(HttpUrl.get(BASE)));
    }

    @Test public void postFailureIsNotReplayed() {
        Scripted direct = new Scripted(new IOException("response lost after commit"));
        Scripted recovery = new Scripted();
        PortalApiTransport transport = new PortalApiTransport(direct, recovery, () -> 10L);
        Request post = new Request.Builder().url(BASE + "/api/v3/work")
                .post(RequestBody.create("{}", MediaType.get("application/json"))).build();
        assertThrows(IOException.class, () -> transport.execute(post, 100));
        assertEquals(1, direct.requests.size());
        assertEquals(0, recovery.requests.size());
    }

    @Test public void recoveryExpiresAndSystemDnsIsUsedAgain() throws Exception {
        AtomicLong now = new AtomicLong(10);
        Scripted direct = new Scripted(new IOException("system route"), new Reply(200, "{}"));
        Scripted recovery = new Scripted(new Reply(200, PING));
        PortalApiTransport transport = new PortalApiTransport(direct, recovery, now::get);
        assertTrue(transport.probe(BASE, PING::equals));
        now.addAndGet(PortalApiTransport.RECOVERY_TTL_MS);
        assertFalse(transport.recoveryActive(HttpUrl.get(BASE)));
        transport.execute(new Request.Builder().url(BASE + "/api/company").build(), 100);
        assertEquals(2, direct.requests.size());
        assertEquals(1, recovery.requests.size());
    }

    @Test public void customOriginsAndNonHttpsNeverUseRecovery() throws Exception {
        Scripted direct = new Scripted(new Reply(200, "{}"));
        Scripted recovery = new Scripted();
        PortalApiTransport transport = new PortalApiTransport(direct, recovery, () -> 10L);
        for (String origin : Arrays.asList("https://evil.api.vart-portal.ru", "https://example.com",
                "http://api.vart-portal.ru", "https://api.vart-portal.ru:8443")) {
            assertFalse(transport.probe(origin, PING::equals));
        }
        transport.execute(new Request.Builder().url("https://custom.example/api/ping").build(), 100);
        assertEquals(1, direct.requests.size());
        assertEquals(0, recovery.requests.size());
    }

    @Test public void tlsErrorsRemainFailures() {
        PortalApiTransport transport = new PortalApiTransport(
                new Scripted(new SSLHandshakeException("bad certificate")),
                new Scripted(new SSLHandshakeException("bad certificate")), () -> 10L);
        assertFalse(transport.probe(BASE, PING::equals));
        assertFalse(transport.recoveryActive(HttpUrl.get(BASE)));
    }

    @Test public void responseSizeBoundIsEnforced() {
        PortalApiTransport transport = new PortalApiTransport(
                new Scripted(new Reply(200, "payload too large")), new Scripted(), () -> 10L);
        assertThrows(IOException.class, () -> transport.execute(
                new Request.Builder().url(BASE + "/api/company").build(), 4));
    }

    @Test public void alternateResolverNeverReceivesOtherHostnames() throws Exception {
        AtomicInteger calls = new AtomicInteger();
        Dns dns = PortalApiTransport.officialDns(host -> {
            calls.incrementAndGet();
            return List.of(InetAddress.getByName("1.1.1.1"));
        });
        assertThrows(UnknownHostException.class, () -> dns.lookup("example.com"));
        assertEquals(0, calls.get());
        assertEquals(1, dns.lookup("reserve-api.vart-portal.ru").size());
        assertEquals(1, calls.get());
    }

    @Test public void privateLoopbackAndBenchmarkAddressesAreRejected() throws Exception {
        Dns dns = PortalApiTransport.officialDns(host -> {
            List<InetAddress> addresses = new ArrayList<>();
            for (String address : List.of("127.0.0.1", "0.0.0.0", "10.0.0.1", "192.168.1.1",
                    "169.254.1.1", "100.64.0.1", "198.18.0.1", "224.0.0.1", "0.1.2.3",
                    "192.0.2.1", "198.51.100.1", "203.0.113.1", "1.1.1.1")) {
                addresses.add(InetAddress.getByName(address));
            }
            return addresses;
        });
        assertEquals(List.of(InetAddress.getByName("1.1.1.1")), dns.lookup("api.vart-portal.ru"));
    }

    @Test public void productionTransportKeepsDefaultHostnameVerificationAndNoAutomaticRetries() {
        OkHttpClient client = PortalApiTransport.apiClient();
        assertFalse(client.retryOnConnectionFailure());
        assertFalse(client.followRedirects());
        assertFalse(client.followSslRedirects());
        assertSame(new OkHttpClient().hostnameVerifier(), client.hostnameVerifier());
    }

    private static final class Reply {
        final int status;
        final String body;
        Reply(int status, String body) { this.status = status; this.body = body; }
    }

    private static final class Scripted implements Call.Factory {
        final List<Request> requests = new ArrayList<>();
        final ArrayDeque<Object> outcomes = new ArrayDeque<>();
        Scripted(Object... outcomes) { this.outcomes.addAll(Arrays.asList(outcomes)); }
        @Override public Call newCall(Request request) {
            return new Call() {
                private boolean executed;
                private boolean canceled;
                @Override public Request request() { return request; }
                @Override public Response execute() throws IOException {
                    assertFalse(executed);
                    executed = true;
                    requests.add(request);
                    assertFalse("Unexpected extra HTTP execution", outcomes.isEmpty());
                    Object next = outcomes.removeFirst();
                    if (next instanceof IOException) throw (IOException) next;
                    Reply reply = (Reply) next;
                    return new Response.Builder().request(request).protocol(Protocol.HTTP_1_1)
                            .code(reply.status).message("test")
                            .body(ResponseBody.create(reply.body, MediaType.get("application/json"))).build();
                }
                @Override public void enqueue(Callback callback) { throw new UnsupportedOperationException(); }
                @Override public void cancel() { canceled = true; }
                @Override public boolean isExecuted() { return executed; }
                @Override public boolean isCanceled() { return canceled; }
                @Override public Timeout timeout() { return new Timeout(); }
                @Override public Call clone() { return newCall(request); }
            };
        }
    }
}
