"""Use system roots plus the explicitly provisioned private CA, never verify=False."""

import ssl

from opspilot.config import Settings


def client_context(settings: Settings) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if settings.tls_ca_file:
        context.load_verify_locations(cafile=settings.tls_ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
