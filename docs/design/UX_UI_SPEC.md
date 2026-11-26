# Lexis Suite — Especificacao de UX/UI (Etapa 2: Regras em Texto)

Documento normativo que governa a arquitetura de informacao, ergonomia, estados e contratos tecnicos de toda a suíte **Lexis** antes da exploracao visual (Google Stitch + referencias) e construcao final de interface. Zero codigo CSS ou emojis neste documento: apenas decisoes de produto e regras verificaveis.

---

## 1. Tese de Produto & Diagnostico da Arquitetura Atual

O **Lexis Suite** e uma ferramenta pessoal de uso diario continuo (no computador com teclado e no celular com uma mao) voltada para quatro fluxos reais: triagem lexica acelerada com $i+1$, ditado e imersao auditiva, curadoria para o Anki Desktop e telemetria CEFR.

### Problemas Estruturais Mapeados na Versao Atual
1. **Dois sistemas visuais sobrepostos:** O CSS acumulado misturava tokens do tema neon inicial (`#00f2fe`, glassmorphism pesado, botoes grandes) com tokens do redesign `deep navy/lavender` (`#080c12`, `#65e1d8`, `#b19aff`), gerando contrastes irregulares e estilos duplicados.
2. **Excesso de chrome acima da dobra no celular:** Somando topbar, breadcrumb, faixa de KPIs, barra de selecao de deck, abas de modo e card de progresso, o usuario precisa rolar ou comprimir a palavra em foco.
3. **Poluicao por emojis no lugar de iconografia consistente:** Emojis misturados nos botoes, badges, headers e tabelas degradam a leitura tecnica e rendem largura inconsistente entre Windows, Android e iOS.
4. **Monolito de 6.164 linhas:** Resolvido na **Etapa 1** ao separar `vocab_review_app.html` (`HTML`), `static/css/lexis.css` (`CSS`) e `static/js/lexis.js` (`JS`), mantendo compatibilidade total com os endpoints Flask/HTTP e testes Playwright.

### Principio Diretor do Redesign
**Clareza editorial de alta densidade:** a superficie deve desaparecer atras do conteudo em ingles. Cor so entra para sinalizar status semantico (`conhecido`, `gap`, `duvida`), foco do modulo ativo ou alerta critico (falso cognato / erro ortografico).

---

## 2. Arquitetura de Navegacao & Ergonomia (Desktop vs Mobile)

### 2.1 Topbar Unificada (Desktop > 720px)
- **Altura fixa:** `56px` a `60px`, posicionada no topo (`sticky`), sem empilhamento de sub-barras redundantes.
- **Esquerda:** marca `lexis SUITE` com icone geometrico SVG simples (clicavel para voltar ao Modulo 1).
- **Centro:** 4 abas primarias exclusivas (`Vocabulario`, `Listening Studio`, `Anki Hub`, `Analytics`), com indicador de modulo ativo por barra inferior de `2px` e marcador colorido discreto.
- **Direita:** pilula compacta de sincronizacao com a nuvem exibindo estado (`1.507 termos` / `Sincronizando` / `Offline`), seletor rapido de tema (`Escuro` / `Claro`) e avatar `LC`.

### 2.2 Bottom Navigation Bar (Mobile <= 720px via `@container`)
- Barra fixa na base da tela com `env(safe-area-inset-bottom)` e 4 destinos identicos (`Vocab`, `Listening`, `Anki Hub`, `Analytics`).
- Alvos de toque com altura minima de `44px` e largura distribuida igualmente (`flex: 1`) para uso com o polegar sem toques acidentais.
- Topbar no mobile exibe apenas marca + status de nuvem + troca de tema (sem abas duplicadas).

### 2.3 Regra de Silencio Visual (Corte de Ruido)
- **Eliminar a barra de breadcrumb global:** a aba ativa na Topbar/Bottom Nav e o titulo interno de cada modulo ja identificam o contexto sem gastar `36px` verticais extras.
- **Substituicao integral de emojis por icones SVG (`stroke-width: 1.5px` a `2px`):** todos os botoes de acao, badges de status e abas usam SVG vetorial uniforme.

---

## 3. Regras Tela a Tela dos 4 Modulos

### Modulo 1 — Vocabulario (Triagem & Chunks)
Objetivo primario: avaliar o maior volume de termos e chunks nativos por minuto com zero atrito e foco absoluto na palavra e na frase $i+1$.

1. **Faixa Unificada de Contexto (Acima do Cartao):**
   - Reunir em uma unica linha compacta: seletor de subdeck (`01k`..`10k`, `pv-top150`, `pv-all`, `collocations`, `idioms`), badge CEFR atual (`B1 · 74,6%`), seletor de modo (`Foco`, `Grade`, `Fila Anki`) e os 3 KPIs tabulares (`Conhecidos`, `Gaps`, `Duvidas`).
   - Abaixo da faixa, exibir apenas uma linha de progresso continua de `4px` a `5px` de altura.
   - **Sprints de Alta Alavanca (`pv-top150`, `02k`, `Podcast de Gaps`):** no desktop aparecem em faixa discreta colapsavel; no mobile ficam acessiveis por menu compacto ou atalho no topo do deck para nao empurrar a palavra para fora da primeira dobra.
2. **Hierarquia do Cartao no Modo Foco (Top -> Bottom):**
   - **Linha de metadados:** subdeck, classe gramatical (POS), fonte da frase (`MWLD` ou `Mairo Vergara`), badge `Falso Amigo` (somente quando detectado) e dois botoes utilitarios discretos: `Jev IA [J]` e `Audio [A]`.
   - **Bloco da Palavra:** termo principal em tipografia fluida (`clamp`, nunca menor que `28px`, maximo `44px`), acompanhado da transcricao fonetica IPA em fonte monoespacada.
   - **Alertas Condicionais:** banner de Falso Cognato (cor de alerta + icone obrigatorio) e painel colapsado de Diagnostico Jev aparecem somente quando acionados ou aplicaveis.
   - **Bloco de Significado:** definicao em ingles (`EN`) e traducao objetiva (`PT`) dentro de superficie interna com raio concentrico.
   - **Bloco de Contexto $i+1$:** frase autentica com o termo alvo (ou chunk inteiro, mesmo flexionado/separavel) destacado visualmente + traducao `PT` + botao `Outro Exemplo [E]` e `Curar com Jev` quando aplicavel.
   - **Bloco de Decisao (Fixo na zona de alcance):** 3 botoes principais com largura igual (`Conheco [1]`, `Nao Sei [2]`, `Duvida [3]`) + linha auxiliar discreta (`Voltar Carta [Z]`, `Pular [Espaco]`).
3. **Modo Grade (Batch Matrix):**
   - Filtros (`Status`, `POS`, busca global `66k`) alinhados em barra unica.
   - Acoes em lote (`Auto-Aprovar Cognatos Jev`, `Marcar Restantes`, `Salvar Lote`) no topo da tabela, nunca visiveis durante o Modo Foco.
   - Em telas estreitas (`<= 720px`), a tabela converte linhas em cartoes empilhados ou rolagem horizontal explicita com coluna de acao fixa.

### Modulo 2 — Listening Studio (Video Ditado, Escuta as Cegas & Imersao Continua)
Objetivo primario: treinar compreensao auditiva real sem revelar a resposta antes da formulacao da hipotese pelo usuario.

1. **Seletor de Submodo:** controle segmentado unico no topo do modulo (`Video Ditado`, `Escuta as Cegas`, `Imersao Continua`), mantendo titulo e descricao de 1 linha.
2. **Submodo Video Ditado:**
   - Seletor de fonte (`YouTube` vs `Video Local .mp4 + .srt`) compacto em 1 linha no desktop, empilhado sem overflow no mobile.
   - Container de video com `aspect-ratio: 16 / 9` reservado antes do carregamento (zero saltos de layout).
   - **Word Slots em Tempo Real:** posicionados imediatamente acima do campo de texto com 4 estados visuais claros + semanticos: `pending` (tracejado), `current` (borda acento), `completed` (verde + palavra revelada), `typo` (ambar + pulso sutil).
   - **Dica Ortografica Inteligente (Levenshtein <= 2):** banner inline instrutivo logo abaixo do input sem bloquear digitacao nem punir com vermelho agressivo.
   - **Controles de Frase:** navegacao livre (`Anterior` / `Proxima`), velocidade (`1.0x` / `0.75x` / `0.5x`), `Ouvir mais 2s`, `Repetir [Alt+R]`, `Pista [Alt+H]`, `Revelar` e `+ Enviar para Anki`.
3. **Submodo Escuta as Cegas:**
   - Workspace de 2 colunas no desktop (Player central + Sidebar com progresso da sessao e guia de 4 passos) colapsando em 1 coluna no mobile.
   - Waveform visual e botao `Revelar transcricao` obrigatoriamente ocultando texto EN/PT ate o clique intencional.
4. **Submodo Imersao Continua (Podcast Pessoal):**
   - Player centrado em audio continuo para uso com tela bloqueada e fone Bluetooth (`MediaSession API`).
   - Controles diretos de origem (`Gaps i+1`, `Conhecidos`, `Deck Atual`, `Mix Global`), cadencia (`1x`, `2x Reflexivo: 1x -> Pausa -> 2x`, `3x Shadowing`), intervalo de silencio (`1.5s` a `6.0s`) e `Modo Cego` (oculta texto na tela).
   - Fila lateral rolavel com fade nas extremidades sinalizando continuidade.

### Modulo 3 — Anki Hub (Pipeline SRS $i+1$)
Objetivo primario: dar governanca transparente do funil entre triagem no celular e criacao de cartoes no Anki Desktop.

1. **4 Cartoes de Telemetria Tabulares (Grid 4 colunas -> 2x2 no mobile):**
   - `Status AnkiConnect` (icone + texto claro: `Online` vs `Anki Desktop Fechado`), `Prontos para Injecao (i+1)`, `Retidos pela Trava i+2`, `Cartoes Vinculados no Anki`.
2. **Regra de Honestidade de Ambiente:**
   - Quando o usuario estiver acessando pela nuvem (Cloud Run), o card de status AnkiConnect deve informar explicitamente que a injecao fisica requer rodar o servidor local no PC junto com o Anki Desktop, mantendo visiveis a fila e o preview auditivo.
3. **Area Operacional (2 colunas -> 1 coluna no mobile):**
   - Esquerda: tabela `Fila Prioritaria Pronta (Top 1k -> 10k)` ordenada por frequencia, com badge do deck, frase $i+1$, definicao PT e botao de preview auditivo.
   - Direita: historico auditavel das ultimas injecoes no baralho com data de vinculacao.

### Modulo 4 — Analytics (Radar CEFR)
Objetivo primario: transformar numeros de triagem em decisao imediata sobre qual deck atacar em seguida.

1. **4 Cartoes de Resumo (Grid 4 colunas -> 2x2 no mobile):**
   - `Nivel Operacional Estimado`, `Vocabulario Mapeado`, `Indice de Dominio Direto (%)`, `Protecao Cognitiva Jev (Falsos Amigos)`.
2. **Curva de Dominio MWLD (`01k` a `10k`) & Estruturas Nativas (`pv-top150`, `pv-all`, `collocations`, `idioms`):**
   - Cada faixa exibe legenda (`Conhecido` / `Gap` / `Duvida`), contagem exata (`avaliados / total`) e barra empilhada clicavel.
   - **Regra de acao direta:** clicar em qualquer faixa navega imediatamente para o Modulo `Vocabulario` ja posicionado naquele subdeck.
3. **Distribuicao por Classe (POS) & Atividade Recente:**
   - Grade enxuta com contadores alinhados a direita (`tabular-nums`) e mini grafico de barras dos ultimos 14 dias.

---

## 4. Estados Obrigatorios & Resiliencia

| Estado | Regra Obrigatoria de Interface |
| :--- | :--- |
| **Loading** | Exibir placeholder discreto ou texto inline (`Carregando...`) reservando altura para evitar salto de layout; nunca bloquear a tela inteira com overlay modal para chamadas rapidas. |
| **Empty (Fila/Deck zerado)** | Nunca deixar area em branco: mostrar resumo do marco alcancado (ex: `Deck 01k 100% concluido`) e CTA primario apontando para o proximo deck ou para o `Anki Hub`. |
| **Error (Rede / YouTube / Jev)** | Toast nao-intrusivo com mensagem acionavel em portugues claro e acao de recuperacao (ex: `Usar video local` ou `Reenviar pendencias`). |
| **Offline / Anki Fechado** | Manter ditado local, player de audio local e fila em `localStorage` operacionais; nunca apagar rascunhos digitados durante falha de rede. |

---

## 5. Contratos de Qualidade, Acessibilidade e Craft

1. **Iconografia & Zero Emojis:** Proibido uso de emojis em botoes, titulos, badges, logs de UI ou favicon textual; substituir por icones SVG consistentes com alinhamento otico (`translateX(1px)` em triangulos de play).
2. **Cor & Contraste (WCAG 1.4.1 / 1.4.3 / 1.4.11):**
   - Texto normal >= `4.5:1`, texto grande/icones >= `3:1`, bordas de componentes interativos visiveis.
   - Nunca comunicar estado apenas por cor: todo indicador (`Conhecido`, `Gap`, `Duvida`, `Online`, `Falso Amigo`) combina cor + icone ou texto explicito.
   - Suporte obrigatorio a `@media (forced-colors: active)` com bordas e outlines usando palavras-chave do sistema (`CanvasText`, `Highlight`).
   - Misturas dinamicas de cor devem usar `color-mix(in oklab, ...)` e nunca `in oklch` sobre cores neutras.
3. **Temas (Escuro Padrao + Opcao Clara):**
   - Definir token semantico unificado no `:root`, declarar `color-scheme` coerente por tema e aplicar a cor de fundo tambem em `html` para evitar faixa branca em overscroll.
   - Suavizacao de fonte `antialiased` apenas em tema escuro; restaurar padrao no tema claro.
   - Textura `fractalNoise` sutil (`<= 4%` opacidade) em tile `200px` apenas nos temas escuros.
4. **Tipografia & Alinhamento Numerico:**
   - `font-variant-numeric: tabular-nums` em todos os contadores, metricas, temporizadores e colunas numericas.
   - Titulos responsivos com `clamp()` mantendo proporcao maxima `<= 2.5x` o valor minimo (garantindo zoom de `200%` sem corte).
5. **Geometria & Micro-Interacoes (Craft):**
   - **Raios concentricos:** `raio interno = raio externo - padding` em todos os cartoes aninhados e controles segmentados.
   - **Tactilidade:** botoes clicaveis aplicam `transform: scale(0.97)` em `100ms ease-out` no `:active:not(:disabled)` (com listener `touchstart` passivo para iOS Safari e respeito a `prefers-reduced-motion: reduce`).
   - **Contencao de hover:** abas de navegacao e linhas de lista frequentes trocam estado instantaneamente no hover, sem animacoes lentas que geram sensacao de atraso.
   - **Scroll Fades:** listas rolaveis (fila do podcast e tabelas longas) aplicam `mask-image` progressiva nas bordas que ainda tem conteudo para rolar.

---

## 6. Contratos Tecnicos Imutaveis (Preservacao de Testes & API)

Qualquer refactor visual na Etapa 4 e Etapa 7 **DEVE** preservar integralmente os seletores, IDs e assinaturas abaixo para garantir 100% de compatibilidade com [test_listening_browser.cjs](file:///C:/Users/lucas/Projetos_Antigravity/lexis-app/tests/test_listening_browser.cjs) e [vocab_review_server.py](file:///C:/Users/lucas/Projetos_Antigravity/lexis-app/vocab_review_server.py):

- **Navegacao & Modulos:** `switchModule()`, `switchView()`, `.topbar [data-module="..."]`, `.bottom-nav` (instancia unica), `#view-module-vocab`, `#view-module-listening`, `#view-module-anki`, `#view-module-analytics`.
- **Vocabulario (Modo Foco, Grade e Fila):** `#select-subdeck`, `#view-focus`, `#view-batch`, `#view-gaps`, `#focus-word`, `#focus-example`, `#focus-def-en`, `#focus-def-pt`, `#stat-known`, `#stat-unknown`, `#stat-doubt`, `evaluateCurrent()`, `undoLastEvaluation()`, `skipCurrent()`, `triggerJevAnalysis()`, `playCurrentAudio()`.
- **Listening Studio:** `#dictation-input`, `#dictation-word-slots`, `#dictation-start-time`, `#dictation-end-time`, `#submode-video-container`, `#submode-audio-container`, `#submode-podcast-container`, `ytReady`, `ytPlayer`, `currentSourceKey`, `listeningSessions`, `segmentUnlocked`, `segmentAssisted`, `currentSegmentTiming()`, `loadSegment()`, `resetDictationTiming()`, `getCleanTargetTokens()`, `expandContractions()`, `normalizeDictationText()`, `alignDictationTokens()`, `parseSRTorVTT()`, `activateDictationData()`.
- **Regras de DOM & Endpoints:** todos os atributos `id` da pagina devem permanecer estritamente unicos (`new Set(ids).size === ids.length`); zero autoplay oculto de YouTube na inicializacao; rotas `/api/status`, `/api/words`, `/api/subdecks`, `/api/gaps`, `/api/analytics`, `/api/anki-hub`, `/api/immersion-playlist`, `/api/evaluate`, `/api/inject-anki`, `/api/sync-cloud` e `/static/*` inalteradas.

---

## 7. Checklist de Transicao para Etapa 3 (Exploracao Visual)

1. Confirmar com Lucas a aprovacao desta especificacao textual (`docs/design/UX_UI_SPEC.md`).
2. Na **Etapa 3**, executar pesquisa de referencias reais (Mobbin / padroes de flashcard, audio player e analytics) e redigir os prompts estruturados para exploracao visual no **Google Stitch** por modulo (Desktop + Mobile).
3. Somente apos escolher a direcao visual na Etapa 3, construir e validar os novos mockups HTML na **Etapa 4**.
