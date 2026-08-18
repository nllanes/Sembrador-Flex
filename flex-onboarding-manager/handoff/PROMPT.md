# PROMPT — paste this into Cursor

Copy the block below verbatim as your message to the agent.

---

Implement the **Flex Onboarding Manager** screen exactly as designed. Two files are the source
of truth — read both before writing code:

1. `source/flex-onboarding.html` — the complete, working reference design (~46KB, readable,
   self-contained). **Open it in a browser first** to see and feel the intended behavior, then
   read the markup, CSS, and JS. Match its layout, spacing, colors, and interactions exactly.
2. `SPEC.md` — what each stage does, every control, the visual tokens, the behavior checklist,
   and the data shape.

Implement it in this project's stack: **<TELL IT YOUR STACK — e.g. "Next.js + React +
Tailwind", "Vite + React + CSS modules", "plain HTML/CSS/JS">**.

Rules:
- Reproduce the **3-stage flow** (Buscar estaciones → Siembras → Cuentas activas) with the
  numbered step nav and inline KPIs — not separate pages, not big KPI boxes.
- Keep every control and column listed in SPEC.md §3–§4. This is a dense operator tool; do not
  simplify or hide things behind menus.
- Use the exact color values, radii, and font choices from SPEC.md §6. One amber primary per
  context; green/red only for semantic status. All numbers tabular-nums.
- Implement every item in the SPEC.md §7 behavior checklist, especially: filter chips,
  station multi-select + selection bar, the create-siembras modal, and **Siembras grouped by
  state and collapsed by default with independent expand/collapse**.
- Use Leaflet with CartoDB `dark_all` tiles for the map; markers colored by availability,
  selection highlighted, fitBounds to results.
- Keep `STATIONS` / `SIEMBRAS` field names from SPEC.md §8 and wire them to our real data
  source; leave a clear TODO where the API call goes. The reference data is sample data.

Work one stage at a time — flow shell → stage 1 (filters, list, map, selection bar, modal) →
stage 2 (grouped list + detail checklist) → stage 3 — and show me each before moving on.

---

## Notes for you (not for the agent)

- **Hand over the whole folder.** Tell it to read `source/flex-onboarding.html` + `SPEC.md`.
- **Always state your stack** in the prompt where marked — otherwise the agent guesses.
- **One stage at a time** keeps it from rewriting everything and drifting.
- If styling drifts, paste the specific CSS block from the reference and say "use these exact
  styles."
- The reference is interactive: apply a filter, mark stations, press *Crear siembras*, then open
  a state group in stage 2. Seeing it run prevents a lot of misinterpretation.
