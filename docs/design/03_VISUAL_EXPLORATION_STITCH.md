# Lexis Suite — Etapa 3: Exploracao Visual (Google Stitch + Referencias)

Kit operacional da **Etapa 3** derivado integralmente de [UX_UI_SPEC.md](file:///C:/Users/lucas/Projetos_Antigravity/lexis-app/docs/design/UX_UI_SPEC.md). Contem o sistema de tokens-alvo e **4 prompts prontos para copiar e colar no Google Stitch** (Desktop + Mobile) para explorar a direcao visual antes da construcao final dos mockups HTML na Etapa 4.

---

## 1. Direcao Estetica Travada para o Google Stitch

Ao gerar variacoes no Google Stitch, mantenha estas constantes em todas as telas para preservar coerencia de produto:

- **Estetica:** Editorial de alta densidade e silencio visual (sem neon excessivo, sem glassmorphism pesado, sem emojis em nenhum botao ou titulo).
- **Paleta Base (Dark Default):** Fundo `#080c12` ou `#090b0f`, superficie `#101720` / `#11151d`, cartoes `#141b26`, bordas hairline `1px` (`rgba(255,255,255,0.08)`).
- **Sinais Semanticos Cirurgicos:**
  - Modulo Vocabulario / Acento Principal: `#65e1d8` (Cyan contido)
  - Modulo Listening Studio: `#b19aff` (Lavanda)
  - Modulo Anki Hub / Duvida / Alerta Ortografico: `#edc579` (Ambar)
  - Modulo Analytics: `#80b8ff` (Azul)
  - Conhecido: `#10b981` | Gap / Falso Amigo: `#f43f5e`
- **Tipografia & Numeros:** Sans-serif limpa (`Inter` / `Outfit`) + monoespacada (`JetBrains Mono`) para IPA e metricas tabulares (`tabular-nums`).
- **Iconografia:** Icones lineares SVG finos (`1.5px` stroke), zero emojis.
- **Geometria:** Raios concentricos (`20px` externo, `12px` padding -> `8px` interno).

---

## 2. Prompts Prontos para o Google Stitch

### Prompt 1 — Modulo 1: Vocabulario (Modo Foco · Desktop e Mobile)

```text
Design a sleek, high-craft dark-mode web app screen (Desktop 1440px and Mobile 390px) for "Lexis Suite", a personal English vocabulary acquisition platform.

Visual direction:
- Editorial dark craft inspired by Linear and Raycast. Deep obsidian/navy canvas (#090b0f), surface (#11151d), elevated cards (#161b26), crisp 1px hairline borders (rgba(255,255,255,0.08)), zero emojis, thin 1.5px stroke monochrome SVG icons only.
- Typography: Inter for UI, JetBrains Mono with tabular numerals for IPA and counters.

Navigation:
- Desktop top bar (56px height): left "lexis SUITE" geometric mark; center 4 clean tabs ("Vocabulario" active with 2px cyan #65e1d8 underline, "Listening Studio", "Anki Hub", "Analytics"); right compact cloud sync pill ("1.507 termos") and circular "LC" avatar. No duplicate breadcrumb bar.
- Mobile (390px): minimal top header (logo + cloud pill) and fixed ergonomic bottom navigation bar with 4 tabs (Vocab, Listening, Anki Hub, Analytics).

Main content (Vocabulario — Focus Mode):
- Single unified slim context strip above the card: deck selector dropdown ("Deck 02k · A2 · 57,9%"), CEFR badge ("B1 · 74,6%"), view switcher ("Foco" active, "Grade", "Fila Anki"), and 3 tabular counters with tiny semantic icons (1.170 known emerald, 248 gaps coral, 102 doubts amber). Thin 4px progress bar right underneath.
- Centered Focus Card (max-width 760px, 20px outer radius, 12px padding, 8px inner boxes):
  1. Top metadata row: badges "02K", "VERB", "MWLD + Mairo", coral warning badge "Falso Amigo" with triangle icon; right side two subtle utility buttons "Jev IA [J]" and "Audio [A]".
  2. Large bold word headline "pretend" (40px) beside monospace IPA "/priˈtɛnd/".
  3. Subtle amber inline alert banner: "Falso Cognato: significa FINGIR, nao pretender. Pretender = intend."
  4. Meaning inner box: EN pill "to act as if something is true when it is not" and PT pill "fingir, simular que algo e real".
  5. Context i+1 inner box with header "FRASE DE CONTEXTO I+1" and "Outro Exemplo" button: "She tried to pretend that nothing had happened." (with "pretend" highlighted in subtle cyan tint) and Portuguese translation below.
  6. Three equal-width tactile decision buttons at the bottom of the card: "Conheco [1]" (subtle emerald border on hover), "Nao Sei [2]" (coral), "Duvida [3]" (amber).
  7. Minimal footer row: "Voltar Carta [Z]" on left, "Pular [Espaco]" on right.
```

---

### Prompt 2 — Modulo 2: Listening Studio (Video Ditado + Imersao Continua)

```text
Design two dark-mode screens (Desktop 1440px and Mobile 390px) for the "Listening Studio" module of "Lexis Suite", sharing the exact same topbar/bottom-nav design system (#090b0f canvas, #11151d surface, #161b26 card, lavender #b19aff module accent, zero emojis, thin SVG icons).

Top module header:
- Eyebrow badge "LISTENING STUDIO", title "Video Ditado Interativo", and a segmented 3-option pill toggle on the right: "Video Ditado" (active), "Escuta as Cegas", "Imersao Continua".

Screen 2A — Video Ditado:
- 2-column layout on desktop (1.45fr main dictation stage + 1fr compact sidebar), single column on mobile.
- Left card: compact source toolbar ("YouTube" vs "Video Local .mp4 + .srt", preset dropdown "Steve Jobs · Stanford · 178 frases"), 16:9 dark video player container, real-time Word Slots row above the text input showing green completed word pills ("I", "am"), an amber typo pill ("honered"), a lavender active slot, and dashed pending slots.
- Clean dictation text input field with an inline amber Smart Spelling Hint banner underneath: "Dica ortografica: voce digitou 'honered', a grafia correta e 'honored'."
- Action row: "Ouvir mais 2s", "Repetir [Alt+R]", "Pista [Alt+H]", "Revelar", and "+ Enviar para Anki".

Screen 2B — Imersao Continua (Personal Audio Podcast):
- Centered audio studio player card with top status line ("FAIXA 01 / 45 · GAPS I+1" and "MediaSession API Ativa"), word chip ("pretend · /priˈtɛnd/ · 02K"), clean sentence display (with "Modo Cego" toggle to hide text), minimalist 36-bar lavender audio waveform, large circular lavender play button (with optically centered play triangle) flanked by Previous/Next and speed toggle ("1.0x"), and cadence selector ("2x Reflexivo: 1x -> Pausa 2.5s -> 2x").
- Right sidebar: session progress card and scrollable upcoming track queue with soft top/bottom scroll fade.
```

---

### Prompt 3 — Modulo 3: Anki Hub (Pipeline SRS i+1)

```text
Design a dark-mode desktop (1440px) and mobile (390px) screen for the "Anki Hub" module of "Lexis Suite" (#090b0f canvas, #11151d surface, #161b26 cards, amber #edc579 module accent, zero emojis, thin SVG icons, tabular numerals).

Header:
- Eyebrow "ANKI HUB · PIPELINE SRS", title "Central de Injecao i+1", right action group: "Verificar Conexao", "Enriquecer Frases", "Sincronizar Nuvem", quantity dropdown ("Top 10 Gaps"), and primary amber CTA button "Injetar no Anki".

4 KPI Cards (4 columns desktop, 2x2 grid mobile):
1. "STATUS ANKICONNECT" — icon + "Online (v6)" or "Anki Desktop Fechado" with honest helper subtext.
2. "PRONTOS PARA INJECAO (I+1)" — "340" in emerald.
3. "RETIDOS TRAVA I+2" — "10" in amber.
4. "CARTOES NO BARALHO" — "398" in blue.

Main 2-column area (collapses to 1 column on mobile):
- Left (1.45fr): clean hairline data table "Fila Prioritaria Pronta (Top 1k -> 10k)" with columns Deck badge, Termo + POS, Frase i+1 + PT translation, and compact Audio play button.
- Right (1fr): vertical feed "Ultimas Injecoes no Baralho" showing recently linked cards with date chips and sentence previews.
```

---

### Prompt 4 — Modulo 4: Analytics (Radar de Cobertura CEFR)

```text
Design a dark-mode desktop (1440px) and mobile (390px) screen for the "Analytics" module of "Lexis Suite" (#090b0f canvas, #11151d surface, #161b26 cards, blue #80b8ff module accent, zero emojis, thin SVG icons, tabular numerals).

Header:
- Eyebrow "ANALYTICS · TELEMETRIA CEFR", title "Radar de Cobertura Lexica (A1 a C2)", subtitle explaining that clicking any band opens that deck in Focus Mode, and "Atualizar" button.

4 KPI Cards (4 columns desktop, 2x2 mobile):
1. "NIVEL ESTIMADO" — "B1 · Intermediario"
2. "VOCABULARIO MAPEADO" — "1.507" ("1.568 acepcoes")
3. "DOMINIO DIRETO" — "74,6%" ("1.170 conhecidos · 248 gaps · 102 duvidas")
4. "PROTECAO JEV" — "88" ("Falsos amigos monitorados")

Main 2-column area (1.55fr left, 1fr right; 1 column mobile):
- Left card: "Curva de Dominio MWLD (01k a 10k)" with clickable rows showing deck code, CEFR tag, tabular ratio ("847/847 · 100%"), and thin 7px stacked horizontal progress bars (emerald known, coral gaps, amber doubts). Show 01k at 100%, 02k at 57.9%, 03k at 9.9%, 04k at 7.2%, 05k at 5.5%.
- Right column stacked cards:
  1. "Estruturas e Chunks Nativos" with clickable rows for "PV-TOP150 (0/202 · 0%)", "COLLOCATIONS (8/6458)", "IDIOMS (0/1500)".
  2. "Distribuicao POS & Ritmo (14 dias)" with a 2x3 compact POS grid and a minimalist 14-day vertical bar sparkchart.
```

---

## 3. Como fechar a Etapa 3 e iniciar a Etapa 4

1. Rode os prompts acima (ou os dos modulos que priorizar) no **Google Stitch** e traga os prints ou o HTML gerado aqui no chat — ou cole qualquer referencia visual sua.
2. Tambem podemos usar [lexis_redesign_studio.html](file:///C:/Users/lucas/Projetos_Antigravity/lexis-app/docs/mockups/lexis_redesign_studio.html) como base comparativa lado a lado com o que sair do Stitch.
3. Assim que voce escolher a direcao visual vencedora, entramos na **Etapa 4 (Construcao da interface: mockups + validar + iterar)** ja mirando diretamente no novo [lexis.css](file:///C:/Users/lucas/Projetos_Antigravity/lexis-app/static/css/lexis.css) modularizado na Etapa 1.
