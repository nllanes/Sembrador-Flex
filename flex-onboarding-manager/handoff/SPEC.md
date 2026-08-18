# Flex Onboarding Manager — Implementation Spec

> **For:** a coding agent (Cursor) implementing this screen.
> **Reference:** `source/flex-onboarding.html` — open it in a browser. It is the **source of
> truth**: fully working, self-contained, ~46KB, readable. Match it exactly.

---

## 1. What the app does

Manage the onboarding of Amazon Flex drivers, station by station:

```
1  BUSCAR ESTACIONES  →  2  SIEMBRAS  →  3  CUENTAS ACTIVAS
   filter by state /       one file per        completed +
   city / ZIP, mark        station, with       handed-off
   stations                8-step checklist    accounts
```

"**Siembra**" = an onboarding file/case for one station (the user's domain term — keep it).

## 2. Global shell

- **Top bar (60px, sticky):** amber `F` logo tile · title "Flex Onboarding Manager" · subtitle
  "Estaciones · siembras · checklist · handoff". Right: `Importar CSV` (quiet), `Ajustes`
  (ghost), `+ Nueva siembra` (primary amber).
- **Flow nav (sticky under top bar):** the 3 stages as numbered steps with chevrons between
  them. Active step = amber circle + amber underline. Step 2/3 show a count.
  Right side: 3 inline KPIs — **Total** (6), **En proceso** (4, amber), **Activos** (0, green),
  separated by hairlines. *Not* big boxes.
- Only one stage `<section>` is visible at a time.

## 3. Stage 1 — Buscar estaciones

**Filter bar (horizontal, top — never a left column):** `Buscar` (code/name/address),
`Estado` (select), `Ciudad`, `ZIP code`, `Disponibilidad` (Contratando / Lista de espera /
Cerrada). Right: `Aplicar filtros` (primary) + `Limpiar` (quiet). Enter in search = apply.

**Active-filter chips** row appears below when any filter is set; each chip has an ✕ that
clears just that filter.

**Results list (left) + map (right, 420px):**
- List header: "Estaciones Amazon Flex" · result count · segmented `Por estado | Lista` ·
  `Seleccionar todo`.
- Columns: `☑ · Código · Estación/dirección · Ciudad · ZIP · Disponibilidad · Cupos · ⋯`
  - Código in mono amber (e.g. `DMI4`). Two-line cell: station name + address.
  - Disponibilidad as pill: Contratando=green, Lista de espera=amber, Cerrada=red.
  - Cupos = number + thin amber capacity bar.
- **Grouped by state by default:** sticky group header with state chip, "N estaciones",
  "N contratando". `Lista` switches to flat.
- **Empty state before searching:** "Busca estaciones para empezar" — do not show all rows
  until filters are applied (or `Seleccionar todo` is pressed).
- **Map:** dark Leaflet (CartoDB `dark_all` tiles), circle markers colored by availability,
  selected ones enlarged with amber ring; auto-`fitBounds` to results. Footer stats:
  Estaciones visibles / Contratando ahora / Cupos totales.

**Selection bar (appears at the bottom of the list when ≥1 station is marked):** amber top
border, count pill, "N estaciones seleccionadas · STATES · N cupos", then `Deseleccionar`,
`Exportar CSV`, and **`Crear siembras (N)`** (primary).

**Create modal:** choose checklist template (Flex estándar 8 pasos / Flex express 5 pasos /
Solo documentos), list the selected stations, info note "Se creará **una siembra por
estación**…", footer summary + `Cancelar` / `Crear (N)`. Confirming navigates to stage 2.
Closes on ✕, backdrop click, or Escape.

## 4. Stage 2 — Siembras

- Own filter bar: `Buscar` (name/email/station), `Etapa onboarding`, `Estación`, `Aplicar`.
- Header: "Siembras" · record count · `Acciones en lote`.
- Columns: `☑ · Candidato · Estación · Etapa · Progreso · Actualizado · ⋯`
  - Candidato = colored initials avatar + name + email.
  - Etapa as pill; **Progreso** = 8 thin segments (done=green, current=amber, pending=grey)
    with "N/8 pasos" under it.
- **Grouped by state, COLLAPSED by default.** Group header: rotating chevron, state chip,
  "N siembra(s)", "N lista(s) para handoff". Clicking a state expands only that state; each
  group toggles independently. (Spanish plurals must agree.)
- **Detail panel (right, 440px):** name, email · station, stage pill; 2×2 meta grid (Estación,
  Progreso, Creado, Actualizado); the **8-step checklist** with done (struck-through + green
  check) / current (amber outline) / pending states, each with a hint line; footer
  `Avanzar paso` (primary) + `Notas` + ⋯.

**Checklist steps (8):** Crear cuenta Amazon Flex · Subir licencia de conducir · Registro de
vehículo + seguro · Consentimiento background check · Background check aprobado · Cuenta
bancaria (payout) · Instalar app y login de prueba · Handoff al candidato.

## 5. Stage 3 — Cuentas activas
Empty state: "Aún no hay cuentas activas" + explanation + link back to stage 2. When built,
list completed accounts with their assigned station.

## 6. Visual language (copy from the reference, don't reinvent)

Dark UI, **single amber accent**; green/red/blue/violet only for semantic status.

| Role | Value |
|---|---|
| Page / panels | `#070A12` / `#111726` `#151C2E` `#1A2234` |
| Hairlines | `#212B3F`, `#2A3550` |
| Text | `#F2F5FA` → `#C3CCDC` → `#8492AB` → `#64728C` |
| Amber (primary) | `#F59E0B`, hover `#FBBF24`, on-amber ink `#1A1200` |
| Status | green `#34D399` · red `#F87171` · blue `#60A5FA` · violet `#A78BFA` |
| Radii | 6 / 10 / 14 px, pills 99px |

- Fonts: **Inter** (UI) + **Fira Code** (codes, counts, numbers). All numeric cells use
  `font-variant-numeric: tabular-nums`.
- Buttons: exactly one **primary** per context; **ghost** (outlined) for secondary; **quiet**
  (text) for tertiary. Heights 36px / 30px small.
- Rows: 1px hairline separators, hover = panel tint, selected = amber tint + 2px inset amber
  bar. Sticky table headers, uppercase 10px letter-spaced labels.
- Pills (`.tag`) must be `white-space: nowrap`; give their grid column enough width.

## 7. Behaviors checklist
- [ ] Stage nav switches sections; active step styled; map `invalidateSize()` on return to 1.
- [ ] Filters + Enter-to-apply + chips with individual clear + `Limpiar` resets all & selection.
- [ ] Station multi-select (row click toggles), `Seleccionar todo` toggles the filtered set.
- [ ] Selection bar shows live count / states / cupos; drives `Crear siembras (N)`.
- [ ] Map markers recolor by availability, highlight selection, fitBounds to results.
- [ ] Create modal → confirm → jumps to stage 2.
- [ ] Siembras grouped by state, collapsed initially, independent expand/collapse.
- [ ] Row click loads the detail panel + checklist states.
- [ ] Empty states for: no search yet, no active accounts.
- [ ] Responsive: hide map < 1280px, hide detail panel < 1280px.

## 8. Data shape (swap the mock arrays for the real source)
```js
STATIONS = [{ code:"DMI4", name, addr, city, st:"FL", zip:"33014",
              avail:"Contratando"|"Lista de espera"|"Cerrada", cap:42, ll:[lat,lng] }]
SIEMBRAS = [{ name, mail, st:"DMI4 · Miami Gardens", state:"FL",
              stage:"Background check", step:5, total:8, upd:"hace 2 h", color:"#F59E0B" }]
```
Station data in the reference is **plausible sample data** — replace with the real Amazon Flex
station source. Keep the field names and the screen works unchanged.
