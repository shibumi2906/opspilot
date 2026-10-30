import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.HexFormat;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

/** Local readiness and actual JRE/artifact/truststore assertions; no private data exported. */
public final class OpsIdentityProbe {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("health")) {
            var connection = (HttpURLConnection) URI.create("http://127.0.0.1:9000/health/ready").toURL().openConnection();
            connection.setConnectTimeout(1000);
            connection.setReadTimeout(1000);
            try { if (connection.getResponseCode() != 200) System.exit(1); }
            finally { connection.disconnect(); }
            return;
        }
        var version = Runtime.version();
        if (version.feature() != 21 || version.security() < 13 ||
            (version.security() == 13 && version.build().orElse(0) < 9)) {
            throw new IllegalStateException("Security-fixed Java21 required: " + version);
        }
        var artifact = Path.of("/opt/keycloak/lib/lib/main/com.google.guava.guava-33.6.0-jre.jar");
        var hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(artifact)));
        if (!hash.equals("b530942257fb935f8b2cfaa5f8eb5bd59c555fd8e8d01b8ce98912e077ea606c")) {
            throw new IllegalStateException("Fixed Guava artifact mismatch");
        }
        var factory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        factory.init((KeyStore) null);
        int roots = 0;
        for (var manager : factory.getTrustManagers()) {
            if (manager instanceof X509TrustManager trust) {
                for (X509Certificate certificate : trust.getAcceptedIssuers()) {
                    roots++;
                    if (certificate.getSubjectX500Principal().getName().contains("emSign ECC Root CA - G3")) {
                        throw new IllegalStateException("Compromised CA remains trusted");
                    }
                }
            }
        }
        if (roots == 0) throw new IllegalStateException("Empty default truststore");
        System.out.println("Java " + version + "; verified Guava SHA-256 " + hash + "; trusted roots " + roots + "; compromised CA absent");
    }
}
