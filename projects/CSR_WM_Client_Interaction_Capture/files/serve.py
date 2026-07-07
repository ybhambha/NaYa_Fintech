import ssl, os, subprocess, sys, http.server

cert_file = 'localhost.pem'
key_file  = 'localhost-key.pem'

if not os.path.exists(cert_file):
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

PORT = 8443

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    def end_headers(self):
        # Allow mic access on self-signed HTTPS
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        super().end_headers()

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(cert_file, key_file)

with http.server.HTTPServer(('0.0.0.0', PORT), Handler) as httpd:
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    print("")
    print("  IPS Agent HTTPS server is running")
    print("")
    print("  Open Chrome and go to:")
    print("  https://localhost:8443/ui/csr_interface.html")
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
