import ssl, os, subprocess, sys, http.server

# Azure App Service always sets WEBSITE_HOSTNAME; locally it is absent.
# We use this to decide whether to run local self-signed HTTPS (laptop)
# or plain HTTP behind Azure's TLS-terminating proxy (cloud).
IS_AZURE = "WEBSITE_HOSTNAME" in os.environ

cert_file = 'localhost.pem'
key_file  = 'localhost-key.pem'

# Self-signed certificate is ONLY for local https on your laptop.
# On Azure, the platform terminates TLS for us, so we skip all of this.
if not IS_AZURE and not os.path.exists(cert_file):
    print("Generating self-signed certificate...")
    gen_script = (
        "import datetime, ipaddress\n"
        "from cryptography import x509\n"
        "from cryptography.x509.oid import NameOID\n"
        "from cryptography.hazmat.primitives import hashes, serialization\n"
        "from cryptography.hazmat.primitives.asymmetric import rsa\n"
        "key = rsa.generate_private_key(public_exponent=65537, key_size=2048)\n"
        "subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])\n"
        "cert = (x509.CertificateBuilder()\n"
        "    .subject_name(subject).issuer_name(issuer)\n"
        "    .public_key(key.public_key())\n"
        "    .serial_number(x509.random_serial_number())\n"
        "    .not_valid_before(datetime.datetime.utcnow())\n"
        "    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))\n"
        "    .add_extension(x509.SubjectAlternativeName([\n"
        "        x509.DNSName('localhost'),\n"
        "        x509.IPAddress(ipaddress.IPv4Address('127.0.0.1'))]),\n"
        "        critical=False)\n"
        "    .sign(key, hashes.SHA256()))\n"
        "open('localhost.pem','wb').write(cert.public_bytes(serialization.Encoding.PEM))\n"
        "open('localhost-key.pem','wb').write(key.private_bytes(\n"
        "    serialization.Encoding.PEM,\n"
        "    serialization.PrivateFormat.TraditionalOpenSSL,\n"
        "    serialization.NoEncryption()))\n"
        "print('Certificate generated OK')\n"
    )
    result = subprocess.run([sys.executable, '-c', gen_script],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout.strip())
    else:
        print("ERROR generating certificate:")
        print(result.stderr[:400])
        print("\nFix: run   pip install cryptography   then try again.")
        sys.exit(1)

# Azure injects the port to listen on via the PORT env var.
# Locally there is no PORT set, so we fall back to 8443 as before.
PORT = int(os.environ.get("PORT", 8443))

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_head(self):
        # Serve the app at the ROOT url so the shareable link is just
        #   https://<host>/
        # instead of
        #   https://<host>/ui/csr_interface.html
        # The browser's address bar stays clean (this is an internal
        # rewrite, not a redirect). The /ui/... path still works too.
        if self.path in ('/', ''):
            self.path = '/ui/csr_interface.html'
        return super().send_head()

    def end_headers(self):
        # Allow mic access / cross-origin isolation
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        super().end_headers()

with http.server.HTTPServer(('0.0.0.0', PORT), Handler) as httpd:
    if not IS_AZURE:
        # LOCAL only: wrap the socket in TLS using the self-signed cert.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print("")
    if IS_AZURE:
        host = os.environ.get("WEBSITE_HOSTNAME", "")
        print(f"  IPS Agent server running on port {PORT} (Azure: plain HTTP behind TLS proxy)")
        if host:
            print(f"  URL: https://{host}/")
    else:
        print("  IPS Agent HTTPS server is running")
        print("")
        print("  Open Chrome and go to:")
        print(f"  https://localhost:{PORT}/")
        print("")
        print("  FIRST VISIT: click Advanced -> Continue to localhost (unsafe)")
        print("  After that the mic will work normally.")
    print("")
    print("  Press Ctrl+C to stop.")
    print("")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.")
