import smtplib, ssl, os, sys
sys.path.insert(0, '.')
from semisector.scheduler import load_env_file
from pathlib import Path
load_env_file(Path('.'))

host = 'smtp.gmail.com'
user = os.getenv('SEMISECTOR_EMAIL_FROM')
pwd  = os.getenv('SEMISECTOR_EMAIL_PASSWORD')
print(f'FROM account: {user}')
print(f'Password length: {len(pwd) if pwd else 0}')

for port, method in [(587, 'STARTTLS'), (465, 'SSL')]:
    try:
        print(f'Trying port {port} ({method})...', end=' ')
        if method == 'SSL':
            s = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            s = smtplib.SMTP(host, port, timeout=15)
            s.starttls()
        s.login(user, pwd)
        s.quit()
        print('SUCCESS!')
        break
    except Exception as e:
        print(f'FAILED: {e}')