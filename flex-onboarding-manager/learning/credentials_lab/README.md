# Laboratorio: credenciales seguras + dominio de correo propio

Dos temas que aparecían en tu idea ("un email en un dominio que tendré y le
guardará un pass"): **cómo guardar credenciales de forma segura** y **cómo
funciona un dominio de correo propio**. Aquí lo aprendes bien hecho.

## Parte 1 — Guardar credenciales de forma segura (`secure_credentials.py`)

La regla más importante en seguridad de credenciales:

| Necesidad | Técnica | ¿Reversible? | Ejemplo |
|-----------|---------|--------------|---------|
| Verificar logins de tus usuarios | **Hashing** (scrypt/bcrypt/argon2) + salt | ❌ No | Contraseña de un usuario de tu app |
| Reutilizar un secreto luego | **Cifrado simétrico** (Fernet/AES) | ✅ Sí (con la clave) | Password de un buzón SMTP/IMAP que tú administras, API keys |

Puntos clave que enseña el demo:

- **Nunca guardes contraseñas en texto plano.**
- Cada password lleva su **salt** aleatorio (evita rainbow tables).
- La verificación usa **comparación en tiempo constante** (`hmac.compare_digest`).
- Para secretos recuperables, **la clave de cifrado va SEPARADA** del dato cifrado
  (en una variable de entorno / gestor de secretos, nunca en el repo).

Ejecutar:

```bash
cd learning/credentials_lab
pip install -r requirements.txt
python secure_credentials.py
```

## Parte 2 — Cómo funciona un dominio de correo propio (conceptos)

Cuando dices "un dominio que tendré y creará emails", esto es lo que hay detrás.
Es tecnología estándar y legítima (la usan todas las empresas):

### Piezas

1. **Dominio** (ej. `tuempresa.com`) — lo registras en un registrador (Namecheap,
   Cloudflare, etc.).
2. **Registros DNS** que hacen que el correo funcione:
   - **MX**: dice qué servidor recibe el correo del dominio.
   - **SPF** (TXT): lista qué servidores pueden enviar en tu nombre (anti-spoofing).
   - **DKIM** (TXT): firma criptográfica de tus emails salientes.
   - **DMARC** (TXT): política de qué hacer si SPF/DKIM fallan.
3. **Servidor / proveedor de correo**:
   - Gestionado: Google Workspace, Zoho Mail, Fastmail, Migadu… (recomendado).
   - Autohospedado: Mailu, Mailcow, Postfix + Dovecot (más control, más trabajo).
4. **Buzones (mailboxes)**: cada dirección `nombre@tuempresa.com` con su contraseña.

### "Catch-all" y alias

- Un **catch-all** recibe todo lo enviado a `*@tuempresa.com` en un solo buzón,
  aunque la dirección no exista. Útil, pero atrae spam.
- Los **alias** redirigen `ventas@` o `soporte@` a un buzón real. Mejor que
  catch-all para uso ordenado.
- Muchos proveedores tienen **API** para crear buzones/alias por programa
  (p. ej. Migadu, Zoho, Google Admin SDK) — así se "auto-crean" direcciones de
  forma legítima para **personas reales** de tu organización.

### Cómo se conecta con guardar el "pass"

Si administras buzones para tu equipo, la contraseña de cada buzón es un
**secreto operativo recuperable** → se guarda **cifrado** (Parte 1, opción 2),
con la clave en un gestor de secretos.

## ⚠️ Nota importante sobre el uso

Crear buzones para **personas reales** de tu organización y guardar sus
credenciales cifradas es legítimo. Fabricar emails desechables para **crear
cuentas en masa en un servicio de terceros** (como Amazon Flex) y saltarse su
verificación de identidad NO lo es, y no forma parte de estos laboratorios.
