# OTP automático (Namecheap Private Email)

## Cómo funciona

Cuando Amazon pide código al Sembrar:

1. Playwright/Appium detecta pantalla OTP
2. El CRM se conecta por **IMAP** a Namecheap:
   - Host: `mail.privateemail.com`
   - Puerto: `993` (SSL)
   - User: email de la siembra
   - Pass: la misma guardada en Credenciales (buzón)
3. Busca correo reciente de Amazon
4. Extrae el código de 6 dígitos
5. Lo pega en Amazon y continúa

## Requisitos

- Dominio con **Namecheap Private Email** (no solo DNS en Namecheap)
- Buzón real creado en https://privateemail.com
- La **password del buzón** = la que guardas en la siembra (la usa Amazon y IMAP)
- MX del dominio apuntando a Private Email

## Config (`.env`)

```env
IMAP_OTP_ENABLED=true
IMAP_HOST=mail.privateemail.com
IMAP_PORT=993
IMAP_OTP_TIMEOUT_S=120
IMAP_OTP_POLL_S=5
```

## Probar IMAP a mano

```powershell
python -c "
from app.mailbox_imap import fetch_amazon_otp
from datetime import datetime, timezone, timedelta
r = fetch_amazon_otp(
  email_addr='tu@tudominio.com',
  mailbox_password='pass-del-buzon',
  since=datetime.now(timezone.utc)-timedelta(minutes=30),
  timeout_s=20,
)
print(r)
"
```
