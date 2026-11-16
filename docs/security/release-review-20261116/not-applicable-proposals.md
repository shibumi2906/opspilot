# Proposed non-applicable requirements

Scope: scripted local recovery4 pilot only. Owner confirmed all43 in [owner review](owner-na-review.json). This is not an acceptance of the other210 requirements or a whole ASVS L2 pass. Existing protected backlog fields remain unchanged.

| ID | Rationale |
|---|---|
| v5.0.0-1.2.6 | No LDAP connector or LDAP query construction exists in the selected profile; owner must approve this applicability decision. |
| v5.0.0-1.2.7 | No XPath query feature exists; OIDC uses JSON rather than XML assertions. |
| v5.0.0-1.2.8 | No LaTeX processor or user-supplied TeX is accepted. |
| v5.0.0-1.3.1 | No WYSIWYG or untrusted HTML authoring; user and model output are displayed as text. |
| v5.0.0-1.3.4 | No user SVG upload or rendering pathway; checked-in SVG assets are trusted source artifacts. |
| v5.0.0-1.3.8 | Application code makes no JNDI queries; the managed IdP's JVM dependency risks remain covered by image scanning. |
| v5.0.0-1.3.9 | No memcache client or server; Redis has a different protocol and restricted ACL. |
| v5.0.0-1.3.11 | The local profile has no SMTP/IMAP connector; simulated notifications are durable local domain records. |
| v5.0.0-1.5.1 | No untrusted application XML parser or SAML pathway; archive/operator inputs are separate trusted local operations. |
| v5.0.0-3.5.5 | No application postMessage receiver; authentication uses top-level redirects and server callback. |
| v5.0.0-4.3.1 | No GraphQL or user-programmable database-expression endpoint. |
| v5.0.0-4.3.2 | No GraphQL schema or introspection endpoint is exposed. |
| v5.0.0-4.4.1 | Progress delivery uses authenticated HTTPS SSE; no WebSocket transport. |
| v5.0.0-4.4.2 | No WebSocket upgrade handshake; SSE separately enforces cookie/session/origin policies. |
| v5.0.0-4.4.3 | No dedicated WebSocket sessions or tokens exist. |
| v5.0.0-4.4.4 | No HTTPS-to-WebSocket session transition exists. |
| v5.0.0-5.1.1 | Product has no user upload feature; protected exports and operator backups are assessed separately. |
| v5.0.0-5.2.1 | No user file acceptance; JSON request bodies and telemetry envelopes have separate size admission controls. |
| v5.0.0-5.2.2 | No user file extension/content acceptance feature; internal backups are authenticated, operator-created artifacts. |
| v5.0.0-5.2.3 | No untrusted user archive extraction; operational restore accepts only authenticated locally generated encrypted backups. |
| v5.0.0-5.4.3 | Application does not redistribute files obtained from untrusted sources; exports are bounded server-generated data. |
| v5.0.0-6.5.2 | No lookup recovery codes or out-of-band codes are enabled; TOTP seed confidentiality is assessed through secret/storage controls. |
| v5.0.0-6.5.4 | No lookup secret or out-of-band code authentication; TOTP digits and timing have their own configured controls. |
| v5.0.0-6.6.1 | No SMS, voice or other PSTN authentication option is enabled. |
| v5.0.0-6.6.2 | No out-of-band challenge delivery; TOTP and OIDC transaction binding are separate reviewed mechanisms. |
| v5.0.0-6.6.3 | No out-of-band code entry mechanism; IdP brute-force control still applies to TOTP. |
| v5.0.0-6.8.3 | No SAML assertion consumption; selected federation protocol is OIDC code plus PKCE. |
| v5.0.0-10.2.2 | One pinned authorization server is supported; metadata issuer validation additionally rejects unexpected issuers. |
| v5.0.0-10.3.1 | Business APIs do not accept user OAuth bearer tokens; BFF access token is consumed only by the pinned IdP userinfo endpoint. |
| v5.0.0-10.3.2 | No delegated OAuth resource-server API; application permissions come from authoritative memberships, not user-supplied scope claims. |
| v5.0.0-10.3.3 | No user OAuth resource-server authorization; BFF identities use pinned issuer plus stable subject. |
| v5.0.0-10.3.4 | No bearer-token resource API; BFF authentication still requires recent MFA assurance from the ID token. |
| v5.0.0-10.4.10 | The app OAuth client is public with S256 PKCE; it is not configured as a confidential OAuth client. |
| v5.0.0-10.5.5 | No OIDC back-channel logout receiver; local revocation and hardened userinfo checks coordinate session termination. |
| v5.0.0-11.4.4 | Application encryption/signing keys are CSPRNG-generated, not derived from passwords; IdP password verification has its own KDF requirement. |
| v5.0.0-12.1.3 | Service authentication uses signed short-lived tokens over validated TLS, not client-certificate identity mapping. |
| v5.0.0-17.1.1 | No WebRTC TURN service or user media relay is part of this application. |
| v5.0.0-17.2.1 | No DTLS media certificate or WebRTC media server exists; ordinary TLS keys have separate lifecycle requirements. |
| v5.0.0-17.2.2 | No DTLS-SRTP negotiation or media encryption profile is exposed. |
| v5.0.0-17.2.3 | No RTP/SRTP media processing or media injection surface exists. |
| v5.0.0-17.2.4 | No SRTP packet parser or media server; HTTP/telemetry malformed input is separately bounded. |
| v5.0.0-17.3.1 | No WebRTC signaling service; API/SSE admission limits are assessed independently. |
| v5.0.0-17.3.2 | No media signaling protocol implementation; malformed JSON/API inputs remain part of general validation requirements. |
