# OTP cuando el dominio solo hace forward a un Gmail madre

## Tu setup (Namecheap dominio + forward)

```
Amazon → Miami01@tudominio.com
              ↓  (forward / catch-all Namecheap)
         madre@gmail.com   ← aquí llega el OTP
```

**No** uses `mail.privateemail.com` (eso es Private Email de pago).
El CRM debe leer el **Gmail madre**.

## Config `.env`

```env
IMAP_OTP_ENABLED=true
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_MOTHER_EMAIL=madre@gmail.com
IMAP_MOTHER_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

`IMAP_MOTHER_PASSWORD` = **App Password** de Google (no la pass normal):

1. Activa 2FA en la cuenta Google
2. https://myaccount.google.com/apppasswords
3. Crea “Correo” → copia la pass de 16 caracteres

## Qué hace Sembrar

1. Amazon manda OTP a `siembra@tudominio.com`
2. Namecheap lo reenvía al Gmail madre
3. CRM entra a `imap.gmail.com` con el Gmail madre
4. Busca mails de Amazon dirigidos a esa siembra
5. Pega el código en Amazon

## Password de la siembra (Amazon)

Sigue siendo la que guardas en el CRM (login Amazon).
**No** tiene que ser la del Gmail madre.

## Checklist Namecheap

- [ ] Dominio comprado
- [ ] Email forwarding / catch-all → Gmail madre
- [ ] Prueba: manda un mail a `prueba@tudominio.com` y llega al Gmail
- [ ] App Password de Gmail en `.env`
- [ ] Reinicia el CRM
