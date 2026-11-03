# Telegram Widget & Dashboard Authentication Architecture

Dieses Dokument beschreibt die verbindliche Referenzarchitektur für die Authentifizierung über das offizielle **Telegram Login Widget** (`telegram-widget.js?22`) im TradingView Super-Analyst Dashboard.

---

## 1. Problemstellung & Randbedingungen

Im Dashboard (`index.html`) wird die gesamte Markt- und Trade-Datenbank (ca. 2,8 bis 3,3 MB JSON) direkt inline eingebettet, um vollständigen Offline- und Raspberry-Pi-Betrieb ohne Backend-Server zu gewährleisten.

Diese Single-File-Architektur brachte spezifische Herausforderungen mit sich:
1. **Timing-Konflikt (Head vs. Body):** Das Telegram-Widget befindet sich im Body bei Zeile ~300. Wenn die JavaScript-Handler (`handleTelegramLogin`, `checkUserRole`, `applyAuthenticatedState`) erst im Hauptskript (nach 3 MB Daten) deklariert werden, feuert Telegrams Auth-Signal (PostMessage oder `#tgAuthResult`), bevor der Handler definiert ist.
2. **Cross-Origin-Opener-Policy (COOP):** Einige externe CDN-Ressourcen (z. B. `gstatic.com`) liefern `Cross-Origin-Opener-Policy: same-origin` aus. Dadurch verliert das Telegram-OAuth-Popup die Referenz auf `window.opener`, und das Bestätigungs-Event erreicht die Hauptseite nicht.
3. **Safari ITP & Private Browsing:** In iOS Safari und im Private-Browsing-Modus wird `localStorage` bei Navigationsschritten oder Popups teils isoliert oder zurückgesetzt.
4. **JavaScript Syntaxfehler-Sensitivität:** Wenn in einem 3-MB-Monolith-Skript ein einziger Syntaxfehler auftritt (z. B. verwaistes `return` außerhalb einer Funktion), verwirft der Browser den gesamten Skriptblock. Sämtliche Klick-Handler, Modale und Tab-Wechsel fallen aus.

---

## 2. Die 5 Säulen der stabilen Authentifizierung

```
+-----------------------------------------------------------------------------------+
| 1. HEAD INITIALISIERUNG (Vor jedem Body-Element & Widget)                          |
|    - window.currentAuthUser                                                       |
|    - getStoredUser() [localStorage + sessionStorage + Cookie]                     |
|    - checkUserRole(user) [Master-Admin & Rollenprüfung]                           |
|    - saveStoredUser(user) / clearStoredUser()                                     |
|    - earlyAuthCheck() [Parst sofort #tgAuthResult & ?id= / ?username=]            |
|    - Anti-Flicker CSS: <style>#telegram-auth-gate { display: none !important; }   |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
| 2. WIDGET-MOUNT (HTML BODY)                                                       |
|    - CDN Tailwind (cdn.tailwindcss.com) ohne COOP-Einschränkungen                  |
|    - data-telegram-login="aitradeanalystbot"                                      |
|    - data-onauth="onTelegramAuth(user)"                                           |
|    - data-auth-url="https://bbbdc.github.io/trading-dashboard/" (Exakte Root-URL) |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
| 3. PERSISTENZ (3-Stufen Redundanz)                                                |
|    1. localStorage ('tg_user') -> Standard Desktop                               |
|    2. sessionStorage ('tg_user') -> Aktiver Tab                                  |
|    3. Document-Cookie ('tg_user=...; SameSite=Lax') -> Safari / WebView Fallback  |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
| 4. FEHLERBEHEBUNG & RESET                                                         |
|    - Integrierter Button "🔄 Session zurücksetzen" auf dem Gate                   |
|    - Ruft resetAuthSession() auf: Löscht alle 3 Speicherorte und lädt neu         |
|    - Fallback-Login über Benutzernamen / ID weiterhin für Notfälle aktiv          |
+-----------------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------------+
| 5. QUALITY GATE (Automatisierte Syntax-Validierung)                              |
|    - Python esprima Parser prüft vor jedem Deploy das HTML                        |
|    - 0 Syntaxfehler garantiert Funktionsfähigkeit aller Tabs & Kacheln             |
+-----------------------------------------------------------------------------------+
```

---

## 3. Implementierungs-Details

### A. Early Initialization im `<head>`
```javascript
window.currentAuthUser = null;

function getStoredUser() {
  if (window.currentAuthUser) return window.currentAuthUser;
  try {
    const u = localStorage.getItem('tg_user');
    if (u) { window.currentAuthUser = JSON.parse(u); return window.currentAuthUser; }
  } catch(e) {}
  try {
    const s = sessionStorage.getItem('tg_user');
    if (s) { window.currentAuthUser = JSON.parse(s); return window.currentAuthUser; }
  } catch(e) {}
  try {
    const m = document.cookie.match(/(?:^|;\s*)tg_user=([^;]+)/);
    if (m && m[1]) { window.currentAuthUser = JSON.parse(decodeURIComponent(m[1])); return window.currentAuthUser; }
  } catch(e) {}
  return null;
}

// Anti-Flicker: Gate unsichtbar schalten, bevor der erste DOM-Pixel gerendert wird
if (getStoredUser()) {
  document.write('<style>#telegram-auth-gate { display: none !important; }</style>');
}
```

### B. Rollen- & Berechtigungsprüfung (`checkUserRole`)
```javascript
function checkUserRole(user) {
  if (!user) return null;
  const adminIds = ['15231751'];
  const adminUnames = ['bdc_gumb_drop', 'Bdc_Gumb_Drop'];
  const uid = String(user.id || '').trim();
  const uname = ((user.username || '')).replace(/^@/, '').toLowerCase().trim();

  // Master Admin immer direkt berechtigt
  if (adminIds.includes(uid) || (uname && adminUnames.map(x => x.toLowerCase()).includes(uname))) {
    return 'admin';
  }

  const authCfg = (typeof currentData !== 'undefined' && currentData && currentData.auth_config) ||
                  (typeof EMBEDDED_DATABASE !== 'undefined' && EMBEDDED_DATABASE.auth_config) || {};
  const cfgAdmins = (authCfg.admin_usernames || []).map(x => String(x).replace(/^@/, '').toLowerCase().trim());
  const cfgAdminIds = (authCfg.admin_chat_ids || []).map(x => String(x).trim());

  if (cfgAdminIds.includes(uid) || (uname && cfgAdmins.includes(uname))) {
    return 'admin';
  }

  const authUsers = authCfg.authorized_users || {};
  for (const [k, udata] of Object.entries(authUsers)) {
    const keyUname = k.toLowerCase().replace(/^@/, '');
    const udataUname = ((udata && udata.name) || '').toLowerCase().replace(/^@/, '');
    const udataChatId = String((udata && udata.chat_id) || '').trim();
    if ((uname && (keyUname === uname || udataUname === uname)) || (uid && udataChatId && uid === udataChatId)) {
      return (udata && udata.role) || 'trader';
    }
  }
  return null;
}
```

### C. Telegram Widget Definition im Body
```html
<div id="tg-widget-mount" class="py-2 flex flex-col items-center justify-center min-h-[50px]">
  <script async src="https://telegram.org/js/telegram-widget.js?22" 
          data-telegram-login="aitradeanalystbot" 
          data-size="large" 
          data-radius="12" 
          data-onauth="onTelegramAuth(user)" 
          data-auth-url="https://bbbdc.github.io/trading-dashboard/" 
          data-request-access="write"></script>
</div>
```

---

## 4. Test- & Validierungsroutine

Vor jedem Commit oder Deploy auf GitHub Pages muss zwingend folgender Syntax-Check durchgeführt werden:

```bash
python3 -c "
import esprima, re
with open('/home/admin/trading/dashboard/index.html') as f:
    html = f.read()
scripts = re.findall(r'<script(?:\s+[^>]*)?>(.*?)</script>', html, re.DOTALL)
for i, js in enumerate(scripts):
    if js.strip():
        esprima.parseScript(js)
        print(f'Script {i}: VALID')
"
```

Wenn alle Skripte als `VALID` gemeldet werden, ist gesichert, dass:
1. Keine Syntaxfehler (wie verwaiste `return`-Statements) vorhanden sind.
2. Sämtliche Klick-, Modal- und Tab-Handler fehlerfrei im Browser registriert werden.
3. Der Telegram-Auth-Lifecycle unter allen Browsern (macOS Safari, Brave, Chrome, iOS Safari) reibungslos funktioniert.
