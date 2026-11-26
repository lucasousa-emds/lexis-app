    let currentWords = [];
    let currentIndex = 0;
    let currentBatchOffset = 0;
    const batchLimit = 25;
    let batchLocalStates = {};
    let currentAudioObj = null;
    let searchDebounceTimeout = null;
    let currentDeckStats = null;
    let focusReviewHistory = [];

    // Inicialização Inteligente: Carrega automaticamente o deck ativo em estudo (não concluído)
    document.addEventListener("DOMContentLoaded", async () => {
      setupKeyboardShortcuts();

      const statusData = await fetchStatus();

      // Determinar o deck atual sendo estudado
      const select = document.getElementById("select-subdeck");
      const activeServerDeck = (statusData && statusData.active_subdeck) || "02k";
      const completedDecks = new Set((statusData && statusData.completed_subdecks) || []);
      const savedDeck = localStorage.getItem("lexi_selected_subdeck");

      let targetDeck = activeServerDeck;
      // Se houver preferência salva e ela NÃO for um deck já 100% concluído:
      if (savedDeck && !completedDecks.has(savedDeck)) {
        const exists = Array.from(select.options).some(o => o.value === savedDeck);
        if (exists) {
          targetDeck = savedDeck;
        }
      }

      select.value = targetDeck;
      localStorage.setItem("lexi_selected_subdeck", targetDeck);

      await loadWords(0);
    });

    // Notificações Toast
    function showToast(msg, isSuccess = true) {
      const container = document.getElementById("toast-container");
      const toast = document.createElement("div");
      toast.className = "toast";
      toast.style.borderColor = isSuccess ? "var(--accent-cyan)" : "var(--color-unknown)";
      toast.innerHTML = `<span>${isSuccess ? '✓' : '⚠️'}</span> <span>${msg}</span>`;
      container.appendChild(toast);
      setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
      }, 3500);
    }

    // Carregar Estatísticas Gerais do Mapa
    async function fetchStatus() {
      try {
        const res = await fetch("/api/status");
        const data = await res.json();
        if (data.stats) {
          document.getElementById("stat-known").innerText = data.stats.acepcoes_conhecidas || 0;
          document.getElementById("stat-unknown").innerText = data.stats.acepcoes_desconhecidas || 0;
          document.getElementById("stat-doubt").innerText = data.stats.acepcoes_duvida || 0;
        }
        const readyCount = (data.ready_gaps !== undefined) ? data.ready_gaps : (data.unlinked_gaps || 0);
        const gapEl = document.getElementById("header-gap-count");
        if (gapEl) {
          gapEl.innerText = readyCount;
          gapEl.style.display = readyCount > 0 ? "inline-block" : "none";
        }
        return data;
      } catch (err) {
        console.error("Erro ao buscar status:", err);
        return null;
      }
    }

    // Carregar Palavras da API (Filtros silenciosos automáticos sem poluição)
    async function loadWords(offset = 0) {
      const subdeck = document.getElementById("select-subdeck").value;
      const status = document.getElementById("select-status").value;
      const pos = document.getElementById("select-pos").value;
      const search = document.getElementById("input-search").value.trim();

      // Skip stopwords e group_by_word sempre ativos silenciosamente por padrão
      const url = `/api/words?subdeck=${subdeck}&status=${status}&pos=${pos}&skip_functional=true&group_by_word=true&search=${encodeURIComponent(search)}&limit=${batchLimit}&offset=${offset}`;
      try {
        const res = await fetch(url);
        const data = await res.json();
        currentWords = data.words || [];
        currentIndex = 0;
        currentBatchOffset = offset;
        if (offset === 0) {
          focusReviewHistory = [];
        }
        updateUndoButtonState();

        // Atualizar Dashboard de Métricas
        if (data.deck_stats) {
          currentDeckStats = data.deck_stats;
          updateDashboardStats(currentDeckStats);
        }

        // Atualizar views
        renderCurrentFocusCard();
        renderBatchTable(data.total || 0);
      } catch (err) {
        console.error("Erro ao carregar palavras:", err);
      }
    }

    function updateDashboardStats(ds) {
      // CEFR Badge do Deck
      if (ds.cefr) {
        const cefrEl = document.getElementById("deck-cefr-text");
        if (cefrEl) cefrEl.innerText = `${ds.subdeck.toUpperCase()} • ${ds.cefr.code}`;
      }
      
      // Nível Global Estimado do Usuário
      if (ds.user_level) {
        const userEl = document.getElementById("user-global-level-text");
        if (userEl) userEl.innerText = `Nível ${ds.user_level.code}`;
      }

      // Contador e Porcentagem
      const evalCount = ds.evaluated || 0;
      const totalCount = ds.total || 0;
      const pct = ds.percent || 0;

      const metricsEl = document.getElementById("deck-metrics-text");
      if (metricsEl) metricsEl.innerText = `${pct}% (${evalCount}/${totalCount})`;
      const fillEl = document.getElementById("focus-progress-fill");
      if (fillEl) fillEl.style.width = `${pct}%`;
    }

    function onSubdeckChange() {
      const subdeck = document.getElementById("select-subdeck").value;
      localStorage.setItem("lexi_selected_subdeck", subdeck);
      currentBatchOffset = 0;
      loadWords(0);
    }

    function reloadWords() {
      currentBatchOffset = 0;
      loadWords(0);
    }

    function debounceSearch() {
      clearTimeout(searchDebounceTimeout);
      searchDebounceTimeout = setTimeout(() => {
        reloadWords();
      }, 300);
    }

    // Função de Highlight Dinâmico da Palavra Alvo na Frase
    function highlightWordInSentence(sentence, word, extraSearch = "") {
      if (!sentence) return "";
      let html = "";
      
      // Se o MWLD já destacou a palavra na frase com <i> ou <b>, converte para o highlight luminoso
      if (/<[bi]>[^<]+<\/[bi]>/i.test(sentence)) {
        html = sentence.replace(/<([bi])>([^<]+)<\/\1>/gi, '<span class="highlight-target">$2</span>');
      } else {
        const clean = sentence.replace(/<[^>]+>/g, '');
        if (!word) {
          html = clean;
        } else if (word.includes(" ")) {
          // Highlight inteligente de Chunks / Expressões / Phrasal Verbs
          const parts = word.trim().split(/\s+/);
          const head = parts[0];
          const tail = parts.slice(1).map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join("\\s+");

          const irregularMap = {
            'say': ['said'], 'go': ['went', 'gone', 'going', 'goes'], 'see': ['saw', 'seen', 'seeing', 'sees'],
            'make': ['made', 'making', 'makes'], 'take': ['took', 'taken', 'taking', 'takes'],
            'come': ['came', 'coming', 'comes'], 'know': ['knew', 'known', 'knowing', 'knows'],
            'get': ['got', 'gotten', 'getting', 'gets'], 'give': ['gave', 'given', 'giving', 'gives'],
            'find': ['found', 'finding', 'finds'], 'think': ['thought', 'thinking', 'thinks'],
            'tell': ['told', 'telling', 'tells'], 'become': ['became', 'becoming', 'becomes'],
            'leave': ['left', 'leaving', 'leaves'], 'feel': ['felt', 'feeling', 'feels'],
            'bring': ['brought', 'bringing', 'brings'], 'buy': ['bought', 'buying', 'buys'],
            'teach': ['taught', 'teaching', 'teaches'], 'write': ['wrote', 'written', 'writing', 'writes'],
            'run': ['ran', 'running', 'runs'], 'stand': ['stood', 'standing', 'stands'],
            'lose': ['lost', 'losing', 'loses'], 'pay': ['paid', 'paying', 'pays'],
            'meet': ['met', 'meeting', 'meets'], 'sit': ['sat', 'sitting', 'sits'],
            'speak': ['spoke', 'spoken', 'speaking', 'speaks'], 'read': ['read', 'reading', 'reads'],
            'break': ['broke', 'broken', 'breaking', 'breaks'], 'blow': ['blew', 'blown', 'blowing', 'blows'],
            'call': ['called', 'calling', 'calls'], 'turn': ['turned', 'turning', 'turns'],
            'look': ['looked', 'looking', 'looks'], 'put': ['putting', 'puts'],
            'keep': ['kept', 'keeping', 'keeps'], 'set': ['setting', 'sets'],
            'hold': ['held', 'holding', 'holds'], 'fall': ['fell', 'fallen', 'falling', 'falls'],
            'cut': ['cutting', 'cuts'], 'let': ['letting', 'lets'],
            'pick': ['picked', 'picking', 'picks'], 'work': ['worked', 'working', 'works'],
            'catch': ['caught', 'catching', 'catches'], 'carry': ['carried', 'carrying', 'carries'],
            'clean': ['cleaned', 'cleaning', 'cleans'], 'clear': ['cleared', 'clearing', 'clears'],
            'hang': ['hung', 'hanged', 'hanging', 'hangs'], 'hand': ['handed', 'handing', 'hands'],
            'kick': ['kicked', 'kicking', 'kicks'], 'lay': ['laid', 'laying', 'lays'],
            'wear': ['wore', 'worn', 'wearing', 'wears'], 'shut': ['shutting', 'shuts'],
            'pull': ['pulled', 'pulling', 'pulls'], 'pass': ['passed', 'passing', 'passes'],
            'point': ['pointed', 'pointing', 'points'], 'drop': ['dropped', 'dropping', 'drops'],
            'eat': ['ate', 'eaten', 'eating', 'eats'], 'end': ['ended', 'ending', 'ends'],
            'figure': ['figured', 'figuring', 'figures'], 'fill': ['filled', 'filling', 'fills'],
            'cheer': ['cheered', 'cheering', 'cheers'], 'dress': ['dressed', 'dressing', 'dresses'],
            'grow': ['grew', 'grown', 'growing', 'grows'], 'calm': ['calmed', 'calming', 'calms'],
            'show': ['showed', 'shown', 'showing', 'shows']
          };

          const headForms = [head, `${head}s`, `${head}ed`, `${head}ing`];
          const irr = irregularMap[head.toLowerCase()];
          if (irr) headForms.push(...irr);
          const headPattern = `(?:${headForms.join('|')})`;

          // Suporta chunks contíguos ou com pronomes/objetos intercalados (ex: "turn it off", "pick him up")
          const chunkPattern = new RegExp(`\\b(${headPattern}(?:\\s+[a-zA-Z0-9'\\-]{1,15}){0,2}\\s+${tail})\\b`, 'gi');
          if (chunkPattern.test(clean)) {
            html = clean.replace(chunkPattern, '<span class="highlight-target">$1</span>');
          } else {
            const litPattern = new RegExp(`\\b(${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\\s+/g, '\\s+')})\\b`, 'gi');
            if (litPattern.test(clean)) {
              html = clean.replace(litPattern, '<span class="highlight-target">$1</span>');
            } else {
              html = clean;
            }
          }
        } else {
          // Casar a palavra, plural e flexões regulares
          const pattern = new RegExp(`\\b(${word}[a-zA-Z]*)\\b`, 'gi');
          if (pattern.test(clean)) {
            html = clean.replace(pattern, '<span class="highlight-target">$1</span>');
          } else {
            const irregularMap = {
              'say': ['said'], 'go': ['went', 'gone'], 'see': ['saw', 'seen'], 'make': ['made'],
              'take': ['took', 'taken'], 'come': ['came'], 'know': ['knew', 'known'],
              'get': ['got', 'gotten'], 'give': ['gave', 'given'], 'find': ['found'],
              'think': ['thought'], 'tell': ['told'], 'become': ['became'], 'leave': ['left'],
              'feel': ['felt'], 'bring': ['brought'], 'buy': ['bought'], 'teach': ['taught'],
              'write': ['wrote', 'written'], 'run': ['ran'], 'stand': ['stood'], 'lose': ['lost'],
              'pay': ['paid'], 'meet': ['met'], 'sit': ['sat'], 'speak': ['spoke', 'spoken'], 'read': ['read']
            };
            const irr = irregularMap[word.toLowerCase()];
            let replaced = false;
            if (irr) {
              for (const v of irr) {
                const pIrr = new RegExp(`\\b(${v})\\b`, 'gi');
                if (pIrr.test(clean)) {
                  html = clean.replace(pIrr, '<span class="highlight-target">$1</span>');
                  replaced = true;
                  break;
                }
              }
            }
            if (!replaced) html = clean;
          }
        }
      }

      // Se houver termo pesquisado diferente da palavra-alvo (ex: busca em todas as frases), destaca também
      if (extraSearch && extraSearch.trim().length >= 2) {
        const s = extraSearch.trim();
        if (s.toLowerCase() !== (word || "").toLowerCase()) {
          const sPat = new RegExp(`\\b(${s}[a-zA-Z]*)\\b`, 'gi');
          html = html.replace(sPat, '<span class="highlight-target" style="box-shadow: 0 0 10px rgba(245,158,11,0.5); border: 1px dashed #f59e0b; color: #fef08a;" title="Termo pesquisado">$1</span>');
        }
      }

      return html;
    }

    // Formatar e Destacar a Palavra Traduzida em Português
    function formatPortugueseSentence(ptSentence, enWord, defPt) {
      if (!ptSentence) return "";
      const wLower = (enWord || "").toLowerCase().trim();
      
      // 1. Se já contém <b> ou <i> da tradução com tag preservada
      if (/<[bi]>[^<]+<\/[bi]>/i.test(ptSentence)) {
        let cleaned = ptSentence;

        // Separar pronomes oblíquos da tag (ex: <b>me ajudaria</b> -> me <b>ajudaria</b>)
        if (!['me', 'him', 'her', 'us', 'them', 'it', 'you'].includes(wLower)) {
          cleaned = cleaned.replace(/<([bi])>(me|te|se|nos|vos|lhe|lhes|o|a|os|as)\s+([^<]+)<\/\1>/gi, '$2 <$1>$3</$1>');
        }

        // Separar artigos/preposições da tag (ex: <b>um carro</b> -> um <b>carro</b>)
        if (!['a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'by'].includes(wLower)) {
          cleaned = cleaned.replace(/<([bi])>(o|a|os|as|um|uma|uns|umas|de|do|da|dos|das|em|no|na|nos|nas|ao|à|aos|às|por|pelo|pela|pelos|pelas)\s+([^<]+)<\/\1>/gi, '$2 <$1>$3</$1>');
        }

        return cleaned.replace(/<[bi]>([^<]+)<\/[bi]>/gi, '<span class="highlight-target">$1</span>');
      }

      const clean = ptSentence.replace(/<[^>]+>/g, '');
      if (!enWord) return clean;

      // 2. Heurística gramatical precisa para verbos modais e auxiliares
      if (wLower === 'would') {
        const condMatch = clean.match(/\b([a-záàâãéèêíïóôõöúçñ]+(?:ria|riam|ríamos))\b/i);
        if (condMatch) {
          return clean.replace(new RegExp(`\\b(${condMatch[1]})\\b`, 'i'), '<span class="highlight-target">$1</span>');
        }
      } else if (wLower === 'will' || wLower === "'ll") {
        const futMatch = clean.match(/\b([a-záàâãéèêíïóôõöúçñ]+(?:rá|rão|rei|remos)|irá|irão|vai|vão)\b/i);
        if (futMatch) {
          return clean.replace(new RegExp(`\\b(${futMatch[1]})\\b`, 'i'), '<span class="highlight-target">$1</span>');
        }
      }

      // 3. Mapeamento de termos frequentes de alta precisão
      const commonTranslations = {
        'this': ['esta', 'este', 'isto', 'essa', 'esse', 'isso'],
        'that': ['aquela', 'aquele', 'aquilo', 'essa', 'esse', 'isso'],
        'these': ['estas', 'estes', 'essas', 'esses'],
        'those': ['aquelas', 'aqueles', 'essas', 'esses'],
        'say': ['disse', 'dizer', 'diz', 'disseram', 'falou'],
        'said': ['disse', 'disseram', 'falou'],
        'not': ['não', 'nao'],
        'what': ['qual', 'que', 'o que'],
        'who': ['quem'],
        'where': ['onde', 'aonde'],
        'when': ['quando'],
        'why': ['por que', 'porque', 'por quê'],
        'how': ['como', 'quanto'],
        'all': ['todos', 'todas', 'todo', 'toda', 'tudo'],
        'one': ['um', 'uma', 'único'],
        'can': ['pode', 'podem', 'posso', 'consigo', 'consegue'],
        'could': ['poderia', 'poderiam', 'podia', 'pude', 'pôde'],
        'should': ['deveria', 'deveriam', 'deve'],
        'must': ['deve', 'devem', 'precisa'],
        'have': ['tem', 'ter', 'tinha', 'têm', 'possuo'],
        'has': ['tem', 'possui'],
        'had': ['tinha', 'tinham', 'havia'],
        'do': ['fazer', 'faz', 'fez', 'faço'],
        'did': ['fez', 'fizeram', 'fiz'],
        'see': ['ver', 'vê', 'vejo', 'viu'],
        'saw': ['viu', 'viram'],
        'push': ['empurrar', 'empurra', 'empurrou', 'pressionar'],
        'pull': ['puxar', 'puxa', 'puxou'],
        'drive': ['dirigir', 'dirige', 'cravou', 'pregar']
      };

      const candidates = commonTranslations[wLower] || [];
      for (const cand of candidates) {
        const p = new RegExp(`\\b(${cand})\\b`, 'i');
        if (p.test(clean)) {
          return clean.replace(p, '<span class="highlight-target">$1</span>');
        }
      }

      return clean;
    }

    let currentExampleIndex = 0;
    let currentSentenceAudioUrl = "";

    function getWordSentences(item) {
      if (item && item.sentences && item.sentences.length > 0) {
        return item.sentences;
      }
      const s = [];
      if (item && item.example_1) {
        let srcLabel = "Dicionário MWLD";
        if (item.chunk_type === "phrasal_verb" || item.pos === "phrasal verb") srcLabel = "Phrasal Verbs in Context";
        else if (item.chunk_type === "collocation" || item.pos === "collocation") srcLabel = "Oxford Collocations";
        else if (item.chunk_type === "idiom" || item.pos === "idiom") srcLabel = "Native Idioms & Chunks";

        s.push({
          en: item.example_1,
          pt: item.example_1_pt || "",
          source: srcLabel,
          theme: item.theme_1 || item.theme || "Conversação & Geral",
          audio: item.audio_url || "",
          nid: null
        });
      }
      if (item && item.example_2) {
        s.push({
          en: item.example_2,
          pt: item.example_2_pt || "",
          source: "Dicionário MWLD",
          theme: item.theme_2 || item.theme || "Conversação & Geral",
          audio: item.audio_url || "",
          nid: null
        });
      }
      if (s.length === 0 && item) {
        s.push({
          en: `The ${item.word} is important.`,
          pt: "Frase de contexto.",
          source: "Geral",
          theme: "Conversação & Geral",
          audio: item.audio_url || "",
          nid: null
        });
      }
      return s;
    }

    function displayExample(sentences, idx, item, searchVal) {
      if (!sentences || sentences.length === 0) return;
      const safeIdx = Math.max(0, Math.min(idx, sentences.length - 1));
      const chosen = sentences[safeIdx];

      // Atualizar tema e indicador de origem da frase de forma elegante e independente
      const themeEl = document.getElementById("focus-theme");
      if (themeEl) {
        const cleanTheme = chosen.theme || item.theme || "Conversação";
        themeEl.innerText = cleanTheme;
        themeEl.title = cleanTheme;
      }
      const sourceEl = document.getElementById("focus-source");
      if (sourceEl) {
        sourceEl.style.display = "inline-flex";
        if (chosen.source === "Mairo Vergara") {
          sourceEl.innerText = "Mairo Vergara";
          sourceEl.className = "source-badge source-mairo";
          sourceEl.title = "Frase do Acervo Mairo Vergara";
        } else {
          sourceEl.innerText = "MWLD";
          sourceEl.className = "source-badge source-mwld";
          sourceEl.title = "Dicionário Merriam-Webster";
        }
      }

      // Exemplo em inglês com destaque
      const exEl = document.getElementById("focus-example");
      if (exEl) {
        exEl.innerHTML = highlightWordInSentence(chosen.en, item.word, searchVal);
      }

      // Tradução em português
      const ptEl = document.getElementById("focus-example-pt");
      if (ptEl) {
        const cleanEn = chosen.en.replace(/<[^>]+>/g, '').trim().toLowerCase();
        if (chosen.pt && chosen.pt.trim().toLowerCase() !== cleanEn) {
          ptEl.innerHTML = formatPortugueseSentence(chosen.pt, item.word, item.definition_pt);
        } else {
          ptEl.innerText = "Traduzindo frase contextual...";
          fetchSentenceTranslation(item, safeIdx);
        }
      }

      // Botão de ciclar com contagem real e botão de curadoria Jev
      const btnCycle = document.getElementById("btn-cycle-example");
      const btnCurate = document.getElementById("btn-curate-example");
      if (sentences.length > 1) {
        if (btnCycle) {
          btnCycle.style.display = "inline-flex";
          btnCycle.innerHTML = `<span>Outro Exemplo [E] (${safeIdx + 1}/${sentences.length})</span>`;
        }
        if (btnCurate) {
          btnCurate.style.display = "inline-flex";
          btnCurate.innerHTML = `<span>Curar com Jev</span>`;
        }
      } else {
        if (btnCycle) btnCycle.style.display = "none";
        if (btnCurate) btnCurate.style.display = "none";
      }

      // Áudio da frase
      currentSentenceAudioUrl = chosen.audio || item.audio_url || "";
    }

    async function curateSentenceWithJev() {
      const item = getFocusItem();
      if (!item) return;
      const sentences = getWordSentences(item);
      if (!sentences || sentences.length <= 1) return;

      const btn = document.getElementById("btn-curate-example");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>⏳</span> <span>Curando...</span>`;
      }

      try {
        const res = await fetch("/api/curate-sentence", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            word: item.word,
            definition: item.definition_en || "",
            sentences: sentences
          })
        });
        const data = await res.json();
        if (data.success && data.best_sentence) {
          const foundIdx = sentences.findIndex(s => s.en.trim() === data.best_sentence.en.trim());
          if (foundIdx !== -1) {
            currentExampleIndex = foundIdx;
            displayExample(sentences, currentExampleIndex, item);
            showToast(`✨ Jev escolheu a melhor frase i+1 (${foundIdx + 1}/${sentences.length}) com contexto autêntico!`, true);
          }
        } else {
          showToast("Aviso: Jev Curador não pôde avaliar no momento.", false);
        }
      } catch (err) {
        console.error("Erro na curadoria Jev:", err);
        showToast("Erro ao conectar à API Jev", false);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `<span>✨</span> <span>Curada [Jev]</span>`;
        }
      }
    }

    // Formatação elegante de definições (remove tags brutas e destaca padrões de uso)
    function formatDefinitionHtml(rawText) {
      if (!rawText) return "";
      let clean = String(rawText).trim();
      clean = clean.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
      // Trata padrões de uso como [often + <i>of</i>] ou [frequentemente + <i>do</i>]
      clean = clean.replace(/\[([^\]]+)\]/g, (match, p1) => {
        const inner = p1.replace(/<([bi])>([^<]+)<\/\1>/gi, '<$1 class="def-em">$2</$1>');
        return `<span class="def-usage-tag">[${inner}]</span> `;
      });
      // Converte tags <i> e <b> residuais para classe estilizada
      clean = clean.replace(/<([bi])>([^<]+)<\/\1>/gi, '<$1 class="def-em">$2</$1>');
      clean = clean.replace(/<br\s*\/?>\s*/gi, '<br>');
      clean = clean.replace(/(<br>){2,}/gi, '<br>');
      clean = clean.replace(/^<br>|<br>$/gi, '');
      return clean.trim();
    }

    // ==========================================
    // RENDERIZAÇÃO DO MODO FOCO (1-POR-1)
    // ==========================================
    function renderCurrentFocusCard() {
      const card = document.getElementById("focus-card");
      if (card) {
        card.style.transition = "none";
        card.style.transform = "none";
        card.style.opacity = "1";
        card.style.borderColor = "";
        card.style.boxShadow = "";
      }
      const searchVal = document.getElementById("input-search").value.trim();

      if (!currentWords || currentWords.length === 0 || currentIndex >= currentWords.length) {
        if (searchVal) {
          document.getElementById("focus-word").innerText = searchVal;
          document.getElementById("focus-subdeck").innerText = "NOVO";
          document.getElementById("focus-pos").innerText = "CUSTOM";
          document.getElementById("focus-ipa").innerText = "";
          document.getElementById("focus-def-en").innerText = `Nenhum exemplo nativo encontrado para "${searchVal}" no acervo de 66.000 notas.`;
          document.getElementById("focus-def-pt").innerHTML = `<button class="btn-primary" style="margin-top:10px; padding: 8px 16px; font-size:13px;" onclick="addCustomWord('${searchVal.replace(/'/g, "\\'")}')">➕ Adicionar "${searchVal}" como Gap I+1 no Anki</button>`;
          document.getElementById("focus-example").innerText = `Exemplo: I heard "${searchVal}" today.`;
          document.getElementById("focus-example-pt").innerText = "Clique no botão acima para cadastrar sua própria frase e significado.";
          document.getElementById("focus-theme").innerText = "✍️ Vocabulário do Dia a Dia";
          document.getElementById("focus-false-cognate").style.display = "none";
          const fcBadge = document.getElementById("focus-badge-false-friend");
          if (fcBadge) fcBadge.style.display = "none";
          return;
        }

        const curDeck = document.getElementById("select-subdeck").value;
        const isFinished = currentDeckStats && currentDeckStats.remaining === 0;
        document.getElementById("focus-word").innerText = isFinished ? "🎉 Deck Concluído!" : "Lote Concluído!";
        document.getElementById("focus-ipa").innerText = isFinished ? "100%" : "✓";
        document.getElementById("focus-def-en").innerText = isFinished
          ? `Todas as palavras do Deck ${curDeck.toUpperCase()} foram avaliadas com sucesso!`
          : "Todas as palavras deste lote foram avaliadas.";

        let nextBtnHtml = "";
        if (curDeck !== "all" && curDeck !== "10k") {
          nextBtnHtml = `<button class="btn-primary" style="margin-top:12px; padding: 10px 20px; font-size:13px; font-weight:700; cursor:pointer;" onclick="advanceToNextSubdeck()">Avançar para o Próximo Deck 🚀</button>`;
        }
        document.getElementById("focus-def-pt").innerHTML = (isFinished && nextBtnHtml)
          ? nextBtnHtml
          : "Selecione outro deck ou avance para a próxima página.";
        document.getElementById("focus-example").innerText = isFinished ? "Parabéns pelo progresso!" : "Excelente trabalho de triagem!";
        document.getElementById("focus-example-pt").innerText = "Nenhuma pendência neste segmento.";
        document.getElementById("focus-theme").innerText = isFinished ? "🏆 100% Dominado" : "Concluído";
        document.getElementById("focus-false-cognate").style.display = "none";
        const fcBadgeFin = document.getElementById("focus-badge-false-friend");
        if (fcBadgeFin) fcBadgeFin.style.display = "none";
        const jevPanelFinished = document.getElementById("focus-jev-panel");
        if (jevPanelFinished) jevPanelFinished.style.display = "none";
        return;
      }

      const item = currentWords[currentIndex];
      document.getElementById("focus-word").innerText = item.word;

      const subdeckBadge = document.getElementById("focus-subdeck");
      const posBadge = document.getElementById("focus-pos");

      let sLabel = (item.subdeck || "").toUpperCase();
      if (item.subdeck === "pv-top150") sLabel = "🎯 TOP 150 PV";
      else if (item.subdeck === "pv-all") sLabel = "📚 PHRASAL VERBS";
      else if (item.subdeck === "collocations") sLabel = "🔗 COLLOCATIONS";
      else if (item.subdeck === "idioms") sLabel = "💡 IDIOMS";
      subdeckBadge.innerText = sLabel;

      let posLabel = (item.pos || "WORD").toUpperCase();
      posBadge.innerText = posLabel;

      if (item.chunk_type === "phrasal_verb" || item.pos === "phrasal verb") {
        posBadge.style.background = "rgba(16, 185, 129, 0.22)";
        posBadge.style.color = "#34d399";
        posBadge.style.borderColor = "rgba(16, 185, 129, 0.4)";
      } else if (item.chunk_type === "collocation" || item.pos === "collocation") {
        posBadge.style.background = "rgba(99, 102, 241, 0.22)";
        posBadge.style.color = "#a5b4fc";
        posBadge.style.borderColor = "rgba(99, 102, 241, 0.4)";
      } else if (item.chunk_type === "idiom" || item.pos === "idiom") {
        posBadge.style.background = "rgba(217, 70, 239, 0.22)";
        posBadge.style.color = "#f0abfc";
        posBadge.style.borderColor = "rgba(217, 70, 239, 0.4)";
      } else {
        posBadge.style.background = "";
        posBadge.style.color = "";
        posBadge.style.borderColor = "";
      }
      document.getElementById("focus-ipa").innerText = item.ipa ? `/${item.ipa}/` : "";
      const themeEl = document.getElementById("focus-theme");
      if (themeEl) {
        themeEl.innerText = item.theme ? item.theme : "Conversação";
      }
      document.getElementById("focus-def-en").innerHTML = formatDefinitionHtml(item.definition_en);
      document.getElementById("focus-def-pt").innerHTML = formatDefinitionHtml(item.definition_pt || "Carregando tradução...");

      // Falso Cognato Preventivo
      const fcAlert = document.getElementById("focus-false-cognate");
      const fcBadge = document.getElementById("focus-badge-false-friend");
      if (item.false_cognate) {
        document.getElementById("focus-false-cognate-text").innerText = item.false_cognate;
        fcAlert.style.display = "flex";
        if (fcBadge) fcBadge.style.display = "inline-flex";
      } else {
        fcAlert.style.display = "none";
        if (fcBadge) fcBadge.style.display = "none";
      }

      // Reset Painel Jev
      const jevPanel = document.getElementById("focus-jev-panel");
      if (jevPanel) jevPanel.style.display = "none";
      const btnJev = document.getElementById("btn-jev-analyze");
      if (btnJev) btnJev.innerHTML = `<span>Jev IA [J]</span>`;

      currentExampleIndex = 0;
      const sentences = getWordSentences(item);
      displayExample(sentences, currentExampleIndex, item, searchVal);

      // Se a definição PT não estiver em cache, traduzir
      if (!item.definition_pt) {
        fetchDefTranslation(item);
      }

      // Atualizar contagem dinâmica nos botões de marcar restantes do lote
      const batchRem = (currentWords && currentWords.length > currentIndex) ? (currentWords.length - currentIndex) : 0;
      const btnFocusBatch = document.getElementById("btn-focus-mark-batch");
      if (btnFocusBatch) {
        btnFocusBatch.innerHTML = `⚡ Marcar Restantes do Lote (${batchRem}) como Conhecidas <span style="opacity:0.7; font-size:11px;">[K]</span>`;
      }
      const btnHeaderBatch = document.getElementById("btn-mark-batch-remaining");
      if (btnHeaderBatch) {
        btnHeaderBatch.innerText = `⚡ Marcar Restantes do Lote (${batchRem}) como Conhecidas`;
      }

      // IMPORTANTE: SEM AUTO-PLAY! O áudio só toca se o usuário clicar ou apertar tecla A
    }

    async function fetchDefTranslation(item) {
      try {
        const res = await fetch("/api/translate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: item.definition_en })
        });
        const data = await res.json();
        if (data.translation) {
          item.definition_pt = data.translation;
          if (currentWords[currentIndex] && currentWords[currentIndex].id === item.id) {
            document.getElementById("focus-def-pt").innerHTML = formatDefinitionHtml(data.translation);
          }
        }
      } catch (e) {
        console.error("Erro ao traduzir definição:", e);
      }
    }

    async function fetchSentenceTranslation(item, exIdx = 0) {
      if (!item) return;
      const sentence = (item.sentences && item.sentences[exIdx]) ? item.sentences[exIdx].en : (exIdx === 0 ? item.example_1 : item.example_2);
      if (!sentence) return;

      try {
        const res = await fetch("/api/translate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: sentence, word: item.word })
        });
        const data = await res.json();
        const cleanRaw = sentence.replace(/<[^>]+>/g, '').trim();
        if (data.translation && data.translation.trim().toLowerCase() !== cleanRaw.toLowerCase()) {
          if (item.sentences && item.sentences[exIdx]) {
            item.sentences[exIdx].pt = data.translation;
          }
          if (exIdx === 0) {
            item.example_1_pt = data.translation;
          } else {
            item.example_2_pt = data.translation;
          }
          if (currentWords[currentIndex] && currentWords[currentIndex].id === item.id && currentExampleIndex === exIdx) {
            document.getElementById("focus-example-pt").innerHTML = formatPortugueseSentence(data.translation, item.word, item.definition_pt);
          }
        }
      } catch (e) {
        console.error("Erro ao traduzir frase:", e);
      }
    }

    // Tocar áudio apenas manualmente com feedback visual
    function playCurrentAudio() {
      if (!currentWords || currentIndex >= currentWords.length) return;
      const item = currentWords[currentIndex];
      const targetAudio = currentSentenceAudioUrl || (item && item.audio_url);
      const btn = document.getElementById("focus-audio-btn");
      if (targetAudio) {
        if (currentAudioObj) {
          currentAudioObj.pause();
        }
        currentAudioObj = new Audio(targetAudio);
        if (btn) btn.classList.add("playing");
        currentAudioObj.onended = () => { if (btn) btn.classList.remove("playing"); };
        currentAudioObj.onerror = () => {
          if (btn) btn.classList.remove("playing");
          showToast("Áudio indisponível para esta frase", false);
        };
        currentAudioObj.play().catch(e => {
          if (btn) btn.classList.remove("playing");
          console.log("Áudio bloqueado:", e);
        });
      } else {
        showToast("Áudio indisponível para esta palavra", false);
      }
    }

    // ==========================================
    // DIAGNÓSTICO COGNITIVO COM TYPESAFE JEV IA
    // ==========================================
    async function triggerJevAnalysis() {
      if (!currentWords || currentIndex >= currentWords.length) return;
      const item = currentWords[currentIndex];
      const btn = document.getElementById("btn-jev-analyze");
      const panel = document.getElementById("focus-jev-panel");

      if (panel.style.display !== "none") {
        panel.style.display = "none";
        return;
      }

      // Se já analisado nesta sessão, renderiza instantaneamente da memória (Zero latência)
      if (item.jev_analysis) {
        renderJevAnalysisContent(item.jev_analysis);
        panel.style.display = "flex";
        return;
      }

      btn.disabled = true;
      btn.innerHTML = `<span aria-hidden="true">⏳</span> <span>Analisando Jev...</span>`;

      try {
        const sentences = getWordSentences(item);
        const curSentence = (sentences && sentences[currentExampleIndex]) ? sentences[currentExampleIndex].en : (item.example_1 || "");

        const res = await fetch("/api/jev-analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            word: item.word,
            definition: item.definition_en || "",
            sentence: curSentence
          })
        });
        const data = await res.json();
        btn.innerHTML = `<span>Jev IA [J]</span>`;

        if (!data.success || !data.analysis) {
          showToast("Aviso: Jev IA temporariamente indisponível.", false);
          return;
        }

        item.jev_analysis = data.analysis;
        renderJevAnalysisContent(item.jev_analysis);
        panel.style.display = "flex";
      } catch (err) {
        btn.innerHTML = `<span>Jev IA [J]</span>`;
        console.error("Erro ao invocar Jev:", err);
        showToast("Erro ao conectar à Jev IA", false);
      } finally {
        btn.disabled = false;
      }
    }

    function renderJevAnalysisContent(an) {
      const badges = document.getElementById("focus-jev-badges");
      const body = document.getElementById("focus-jev-body");

      let cogBadge = "";
      if (an.cognate_type === "transparent") {
        cogBadge = `<span class="badge-jev-cognate badge-cognate-transparent">🟢 Cognato Transparente (${Math.round(an.cognate_confidence * 100)}%)</span>`;
      } else if (an.cognate_type === "false_friend") {
        cogBadge = `<span class="badge-jev-cognate badge-cognate-false_friend">⚠️ FALSO COGNATO (${Math.round(an.cognate_confidence * 100)}%)</span>`;
      } else {
        cogBadge = `<span class="badge-jev-cognate badge-cognate-opaque">⚪ Raiz Opaca / Distinta</span>`;
      }

      badges.innerHTML = cogBadge;

      // Ativação preventiva de falso amigo se Jev detectar alto risco
      if (an.cognate_type === "false_friend" || an.confusion_risk >= 0.70) {
        const fcBadge = document.getElementById("focus-badge-false-friend");
        if (fcBadge) fcBadge.style.display = "inline-flex";
        const fcAlert = document.getElementById("focus-false-cognate");
        if (fcAlert && (!item.false_cognate || fcAlert.style.display === "none")) {
          document.getElementById("focus-false-cognate-text").innerText = `Alerta Jev (${Math.round(an.cognate_confidence * 100)}% conf.): Alto risco de confusão ou falso amigo para falantes de português!`;
          fcAlert.style.display = "flex";
        }
      }

      const riskLabel = an.confusion_risk < 0.35 
        ? `<span style="color:#34d399;">Baixo (${an.confusion_risk})</span>` 
        : (an.confusion_risk < 0.70 ? `<span style="color:#fbbf24;">Moderado (${an.confusion_risk})</span>` : `<span style="color:#f87171;">Alto (${an.confusion_risk})</span>`);

      const sentQLabel = an.sentence_quality >= 1.4 
        ? `<span style="color:#34d399;">🌟 Ótima para Flashcard (${an.sentence_quality})</span>` 
        : (an.sentence_quality >= 0.8 ? `<span style="color:#fbbf24;">Boa Contextualização (${an.sentence_quality})</span>` : `<span style="color:#f87171;">Frase Genérica (${an.sentence_quality})</span>`);

      const hookMap = {
        "latin_root": "🔗 Conectar com a raiz cognata em português",
        "contrast_warning": "🚫 Atenção ao contraste: memorize o que NÃO significa",
        "vivid_scene": "🎬 Ancorar em cena visual ou ação física marcante",
        "usage_pattern": "🧩 Focar na regência e combinação de palavras (collocation)"
      };
      const hookText = hookMap[an.pedagogical_hook] || "Fixação em repetição espaçada";

      body.innerHTML = `
        <div class="jev-panel-grid">
          <div class="jev-metric-box">
            <span class="jev-metric-title">Risco de Confusão</span>
            <span class="jev-metric-val">${riskLabel}</span>
          </div>
          <div class="jev-metric-box">
            <span class="jev-metric-title">Qualidade da Frase i+1</span>
            <span class="jev-metric-val">${sentQLabel}</span>
          </div>
          <div class="jev-metric-box" style="grid-column: 1 / -1;">
            <span class="jev-metric-title">Estratégia Mnemônica Sugerida</span>
            <span class="jev-metric-val" style="color: #c084fc; font-weight: 600;">${hookText}</span>
          </div>
        </div>
      `;
    }

    async function autoApproveBatchCognates() {
      if (!currentWords || currentWords.length === 0) {
        showToast("Nenhuma palavra pendente no lote.", false);
        return;
      }
      const pendingWords = currentWords.slice(currentIndex).map(w => w.word);
      if (pendingWords.length === 0) {
        showToast("Todas as palavras do lote já foram avaliadas.", false);
        return;
      }

      const btn = document.getElementById("btn-auto-approve-cognates");
      if (btn) btn.innerHTML = `<span>⏳</span> <span>Analisando com Jev...</span>`;

      try {
        const res = await fetch("/api/auto-approve-cognates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ words: pendingWords })
        });
        const data = await res.json();
        if (btn) btn.innerHTML = `✨ Auto-Aprovar Cognatos (Jev)`;

        if (data.success) {
          const count = data.approved_count || 0;
          if (count > 0) {
            showToast(`🎉 Jev aprovou automaticamente ${count} cognatos transparentes!`, true);
            await fetchStatus();
            await loadWords(currentBatchOffset);
          } else {
            showToast("Nenhum cognato transparente óbvio encontrado nos termos restantes.", false);
          }
        }
      } catch (e) {
        if (btn) btn.innerHTML = `✨ Auto-Aprovar Cognatos (Jev)`;
        console.error("Erro em autoApproveBatchCognates:", e);
        showToast("Erro ao processar cognatos com Jev", false);
      }
    }

    async function evaluateCurrent(status) {
      if (!currentWords || currentIndex >= currentWords.length) return;

      // Feedback tátil háptico em smartphones/tablets
      if (window.navigator && window.navigator.vibrate) {
        try {
          if (status === "conhecido") window.navigator.vibrate(18);
          else if (status === "desconhecido") window.navigator.vibrate([30, 45, 30]);
          else if (status === "duvida") window.navigator.vibrate(35);
        } catch (e) {}
      }

      const item = currentWords[currentIndex];

      const sentences = getWordSentences(item);
      const safeIdx = Math.max(0, Math.min(currentExampleIndex, sentences.length - 1));
      const chosenSent = sentences[safeIdx] || sentences[0];
      const chosenEx = chosenSent.en;
      const chosenNid = chosenSent.nid || null;
      const subdeckVal = document.getElementById("select-subdeck").value;

      const payload = {
        id: item.id,
        word: item.word,
        pos: item.pos,
        subdeck: subdeckVal,
        definition_en: item.definition_en,
        definition_pt: item.definition_pt,
        example_1: chosenEx,
        card_id: chosenNid,
        status: status
      };

      // Atualização imediata local do progresso do deck (Zero lag)
      if (currentDeckStats) {
        currentDeckStats.evaluated++;
        currentDeckStats.remaining = Math.max(0, currentDeckStats.remaining - 1);
        currentDeckStats.percent = Math.min(100, Math.round((currentDeckStats.evaluated / currentDeckStats.total) * 100));
        updateDashboardStats(currentDeckStats);
      }

      // Atualização imediata dos contadores do cabeçalho
      if (status === "conhecido") {
        const el = document.getElementById("stat-known");
        if (el) el.innerText = parseInt(el.innerText || "0", 10) + 1;
      } else if (status === "desconhecido") {
        const el = document.getElementById("stat-unknown");
        if (el) el.innerText = parseInt(el.innerText || "0", 10) + 1;
      } else if (status === "duvida") {
        const el = document.getElementById("stat-doubt");
        if (el) el.innerText = parseInt(el.innerText || "0", 10) + 1;
      }

      // Atualização imediata da Fila do Anki e feedback ao usuário
      if (status === "desconhecido" || status === "duvida") {
        const gapEl = document.getElementById("header-gap-count");
        if (gapEl) {
          const cur = parseInt(gapEl.innerText || "0", 10) + 1;
          gapEl.innerText = cur;
          gapEl.style.display = "inline-block";
        }
        const actionLabel = status === "desconhecido" ? "Não Sei" : "Dúvida";
        showToast(`📦 "${item.word}" (${actionLabel}) adicionado à Fila do Anki!`);
      }

      // Salva no histórico para possibilitar Desfazer/Voltar (Tecla Z / Backspace)
      focusReviewHistory.push({
        item: JSON.parse(JSON.stringify(item)),
        index: currentIndex,
        exampleIndex: currentExampleIndex,
        evaluatedStatus: status,
        previousUserStatus: item.user_status || null,
        previousStats: currentDeckStats ? JSON.parse(JSON.stringify(currentDeckStats)) : null
      });
      updateUndoButtonState();

      // Próxima carta instantaneamente (Zero delay)
      currentIndex++;
      if (currentIndex >= currentWords.length) {
        const statusFilter = document.getElementById("select-status").value;
        const nextOffset = (statusFilter === "pending") ? 0 : (currentBatchOffset + batchLimit);
        loadWords(nextOffset);
      } else {
        renderCurrentFocusCard();
      }

      // Envio em background
      try {
        const res = await fetch("/api/evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const evalRes = await res.json();
        if (evalRes && evalRes.deck_stats) {
          currentDeckStats = evalRes.deck_stats;
          updateDashboardStats(currentDeckStats);
        }
        fetchStatus();
      } catch (err) {
        console.error("Erro ao salvar avaliação:", err);
      }
    }

    function updateUndoButtonState() {
      const btn = document.getElementById("btn-undo-card");
      if (!btn) return;
      if (focusReviewHistory && focusReviewHistory.length > 0) {
        btn.removeAttribute("disabled");
        const prevWord = focusReviewHistory[focusReviewHistory.length - 1].item.word;
        btn.title = `Voltar para "${prevWord}" e desfazer avaliação (Tecla Z, Backspace ou Ctrl+Z)`;
      } else {
        btn.setAttribute("disabled", "true");
        btn.title = "Nenhuma carta anterior para voltar";
      }
    }

    async function undoLastEvaluation() {
      if (!focusReviewHistory || focusReviewHistory.length === 0) {
        showToast("Nenhuma carta anterior para voltar.", false);
        return;
      }

      const last = focusReviewHistory.pop();
      updateUndoButtonState();

      // Feedback tátil háptico em smartphones/tablets
      if (window.navigator && window.navigator.vibrate) {
        try { window.navigator.vibrate(22); } catch (e) {}
      }

      // 1. Reverter contadores locais imediatamente (Zero lag)
      if (last.evaluatedStatus === "conhecido") {
        const el = document.getElementById("stat-known");
        if (el && parseInt(el.innerText || "0", 10) > 0) {
          el.innerText = parseInt(el.innerText, 10) - 1;
        }
      } else if (last.evaluatedStatus === "desconhecido") {
        const el = document.getElementById("stat-unknown");
        if (el && parseInt(el.innerText || "0", 10) > 0) {
          el.innerText = parseInt(el.innerText, 10) - 1;
        }
        const gapEl = document.getElementById("header-gap-count");
        if (gapEl && parseInt(gapEl.innerText || "0", 10) > 0) {
          const val = parseInt(gapEl.innerText, 10) - 1;
          gapEl.innerText = val;
          if (val === 0) gapEl.style.display = "none";
        }
      } else if (last.evaluatedStatus === "duvida") {
        const el = document.getElementById("stat-doubt");
        if (el && parseInt(el.innerText || "0", 10) > 0) {
          el.innerText = parseInt(el.innerText, 10) - 1;
        }
        const gapEl = document.getElementById("header-gap-count");
        if (gapEl && parseInt(gapEl.innerText || "0", 10) > 0) {
          const val = parseInt(gapEl.innerText, 10) - 1;
          gapEl.innerText = val;
          if (val === 0) gapEl.style.display = "none";
        }
      }

      if (last.previousStats) {
        currentDeckStats = last.previousStats;
        updateDashboardStats(currentDeckStats);
      } else if (currentDeckStats) {
        currentDeckStats.evaluated = Math.max(0, currentDeckStats.evaluated - 1);
        currentDeckStats.remaining++;
        currentDeckStats.percent = Math.min(100, Math.round((currentDeckStats.evaluated / currentDeckStats.total) * 100));
        updateDashboardStats(currentDeckStats);
      }

      // 2. Reposicionar ponteiro da lista
      if (last.index < currentWords.length && currentWords[last.index] && currentWords[last.index].id === last.item.id) {
        currentIndex = last.index;
      } else {
        currentWords.splice(currentIndex, 0, last.item);
      }
      currentExampleIndex = last.exampleIndex || 0;

      // 3. Renderizar imediatamente a carta desfeita
      renderCurrentFocusCard();
      showToast(`↩️ Voltou para "${last.item.word}". Avaliação anterior desfeita! Escolha a nova resposta.`, true);

      // 4. Sincronizar reversão com o servidor em background
      try {
        const subdeckVal = document.getElementById("select-subdeck").value;
        const res = await fetch("/api/revert-evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            word: last.item.word,
            id: last.item.id,
            previous_status: last.previousUserStatus,
            subdeck: subdeckVal
          })
        });
        const evalRes = await res.json();
        if (evalRes && evalRes.deck_stats) {
          currentDeckStats = evalRes.deck_stats;
          updateDashboardStats(currentDeckStats);
        }
        fetchStatus();
      } catch (err) {
        console.error("Erro ao sincronizar reversão com servidor:", err);
      }
    }

    function skipCurrent() {
      if (currentIndex < currentWords.length - 1) {
        currentIndex++;
        renderCurrentFocusCard();
      } else {
        loadWords(currentBatchOffset + batchLimit);
      }
    }

    function markBatchRemainingAsKnown() {
      if (!currentWords || currentWords.length === 0) {
        showToast("Nenhuma palavra carregada neste lote.", false);
        return;
      }

      let markedCount = 0;
      currentWords.forEach(item => {
        // Preserva o que o usuário já marcou como desconhecido ou dúvida neste lote!
        if (batchLocalStates[item.id] !== "desconhecido" && batchLocalStates[item.id] !== "duvida") {
          batchLocalStates[item.id] = "conhecido";
          markedCount++;
        }
      });

      // Atualiza visualmente as caixas (pills) na tabela
      const rows = document.querySelectorAll("#batch-table-body tr");
      rows.forEach((tr, idx) => {
        const item = currentWords[idx];
        if (item && batchLocalStates[item.id] === "conhecido") {
          const group = tr.querySelector(".status-toggle-group");
          if (group) {
            const btns = group.querySelectorAll(".pill-btn");
            btns[0].classList.add("active-known");
            btns[1].classList.remove("active-unknown");
            btns[2].classList.remove("active-doubt");
          }
        }
      });

      // Se o usuário estiver no Modo Foco, alterna para o Modo Grade para que veja as caixas marcadas
      const isFocusView = document.getElementById("view-focus").style.display !== "none";
      if (isFocusView) {
        switchView("batch");
      }

      showToast(`✓ ${markedCount} caixas marcadas como Conhecidas! Revise e clique em "Salvar Lote e Próxima Página".`);

      // Destaque visual no botão de salvar para o usuário ver onde clicar
      const saveBtn = document.querySelector(".btn-batch-save");
      if (saveBtn) {
        saveBtn.style.animation = "none";
        saveBtn.offsetHeight; // trigger reflow
        saveBtn.style.animation = "pulseSave 1.2s ease 2";
      }
    }

    function advanceToNextSubdeck() {
      const select = document.getElementById("select-subdeck");
      const currentIdx = select.selectedIndex;
      if (currentIdx < select.options.length - 1) {
        select.selectedIndex = currentIdx + 1;
        onSubdeckChange();
        showToast(`🚀 Carregando ${select.options[select.selectedIndex].text}...`);
      }
    }

    function cycleExample() {
      if (!currentWords || currentIndex >= currentWords.length) return;
      const item = currentWords[currentIndex];
      const sentences = getWordSentences(item);
      if (sentences.length <= 1) {
        showToast("Esta palavra só possui 1 frase de exemplo disponível no momento.", false);
        return;
      }

      currentExampleIndex = (currentExampleIndex + 1) % sentences.length;
      const searchVal = document.getElementById("input-search").value.trim();
      displayExample(sentences, currentExampleIndex, item, searchVal);
      const chosen = sentences[currentExampleIndex];
      showToast(`Frase ${currentExampleIndex + 1} de ${sentences.length} (${chosen.source})`);
    }

    async function addCustomWord(term) {
      if (!term || !term.trim()) return;
      const phrase = prompt(`Digite uma frase em inglês onde você viu ou ouviu '${term}':`, `I encountered '${term}' in my daily routine.`);
      if (phrase === null) return;
      const defPt = prompt(`Tradução ou significado em português de '${term}':`, term);
      if (defPt === null) return;

      try {
        const res = await fetch("/api/evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            word: term.trim(),
            id: `${term.trim().toLowerCase()}_custom_${Date.now()}`,
            pos: "custom",
            definition_en: phrase.trim(),
            definition_pt: defPt.trim(),
            example_1: phrase.trim(),
            status: "desconhecido"
          })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`🌟 '${term.trim()}' adicionado aos seus Gaps do Anki!`);
          fetchStatus();
          document.getElementById("input-search").value = "";
          reloadWords();
        }
      } catch (err) {
        showToast("Erro ao adicionar palavra customizada.", false);
      }
    }

    async function flagIntruderWord() {
      if (!currentWords || currentIndex >= currentWords.length) return;
      const item = currentWords[currentIndex];
      
      const intruder = prompt(`Frase: "${document.getElementById("focus-example").innerText}"\n\nDigite qual palavra desconhecida você encontrou nesta frase para registrá-la como Gap I+1:`);
      if (!intruder || !intruder.trim()) return;

      try {
        const res = await fetch("/api/flag-intruder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            intruder: intruder.trim(),
            target_word: item.word
          })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`🚩 Palavra '${intruder.trim()}' registrada como Gap de Ouro!`);
          fetchStatus();
          if (item.example_2) cycleExample();
        }
      } catch (err) {
        showToast("Erro ao registrar palavra intrusa.", false);
      }
    }

    // ==========================================
    // RENDERIZAÇÃO DO MODO GRADE EM LOTE
    // ==========================================
    function renderBatchTable(total) {
      const tbody = document.getElementById("batch-table-body");
      tbody.innerHTML = "";
      batchLocalStates = {};
      const searchVal = document.getElementById("input-search").value.trim();

      if (!currentWords || currentWords.length === 0) {
        const tr = document.createElement("tr");
        if (searchVal) {
          tr.innerHTML = `
            <td colspan="5" style="text-align:center; padding: 35px 20px; color: #94a3b8;">
              <div style="font-size: 15px; font-weight: 600; color: #f1f5f9; margin-bottom: 8px;">Nenhuma ocorrência encontrada para "${searchVal}" em 66.000 frases.</div>
              <div style="font-size: 13px; color: #64748b; margin-bottom: 14px;">Você pode adicionar este vocábulo do seu dia a dia diretamente aos seus Gaps.</div>
              <button class="btn-primary" style="padding: 8px 18px; font-size:13px;" onclick="addCustomWord('${searchVal.replace(/'/g, "\\'")}')">➕ Adicionar "${searchVal}" como Gap I+1 no Anki</button>
            </td>
          `;
        } else {
          tr.innerHTML = `<td colspan="5" style="text-align:center; padding: 25px; color: #94a3b8;">Nenhum termo pendente neste filtro.</td>`;
        }
        tbody.appendChild(tr);
        document.getElementById("batch-pagination-info").innerText = `0 resultados`;
        return;
      }

      currentWords.forEach(item => {
        batchLocalStates[item.id] = item.status || "pending";
        const tr = document.createElement("tr");

        const isKnown = batchLocalStates[item.id] === "conhecido";
        const isUnknown = batchLocalStates[item.id] === "desconhecido";
        const isDoubt = batchLocalStates[item.id] === "duvida";

        const fcBadge = item.false_cognate ? `<span style="background:rgba(245,158,11,0.2);color:#fbbf24;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:6px;" title="${item.false_cognate}">⚠️ Falso Amigo</span>` : '';
        const themeBadge = `<span style="background:rgba(56,189,248,0.15);color:#7dd3fc;font-size:10px;padding:1px 6px;border-radius:4px;display:inline-block;margin-bottom:4px;">${item.theme || 'Geral'}</span>`;
        const deckBadge = `<span class="subdeck-badge" style="font-size:9px; padding:1px 5px; margin-left:6px;">${item.subdeck.toUpperCase()}</span>`;

        tr.innerHTML = `
          <td>
            <div class="table-word">
              <span>${item.word}</span>
              ${deckBadge}
              ${fcBadge}
            </div>
            <div style="font-size: 11px; color: #93c5fd;">${item.pos}</div>
          </td>
          <td>
            <div style="font-family: var(--font-mono); font-size: 12px; color: #38bdf8; display: flex; align-items: center; gap: 6px;">
              <span>${item.ipa ? `/${item.ipa}/` : ''}</span>
              ${item.audio_url ? `<button class="audio-btn" style="padding:2px 6px;font-size:11px;" onclick="playAudioUrl('${item.audio_url}')">🔊</button>` : ''}
            </div>
          </td>
          <td>
            <div style="font-size: 13px; color: #f8fafc; font-weight: 500;">${formatDefinitionHtml(item.definition_en)}</div>
            <div style="font-size: 12px; color: #10b981; margin-top: 3px;">${formatDefinitionHtml(item.definition_pt || '')}</div>
          </td>
          <td>
            ${themeBadge}
            ${item.has_mairo ? `<span style="background: rgba(99, 102, 241, 0.2); color: #c7d2fe; border: 1px solid rgba(99, 102, 241, 0.35); padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; margin-left: 4px;">🎙️ ${item.total_sentences} frases</span>` : ''}
            <div style="font-size: 13px; color: #cbd5e1;">${highlightWordInSentence(item.example_1 || '—', item.word, searchVal)}</div>
            ${item.example_1_pt ? `<div style="font-size: 12px; color: #94a3b8; font-style: italic; margin-top: 3px;">${formatPortugueseSentence(item.example_1_pt, item.word, item.definition_pt)}</div>` : ''}
          </td>
          <td style="text-align: center;">
            <div class="status-toggle-group">
              <button class="pill-btn ${isKnown ? 'active-known' : ''}" onclick="setRowStatus('${item.id}', 'conhecido', this)">C</button>
              <button class="pill-btn ${isUnknown ? 'active-unknown' : ''}" onclick="setRowStatus('${item.id}', 'desconhecido', this)">N</button>
              <button class="pill-btn ${isDoubt ? 'active-doubt' : ''}" onclick="setRowStatus('${item.id}', 'duvida', this)">D</button>
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });

      const pageNum = Math.floor(currentBatchOffset / batchLimit) + 1;
      const totalPages = Math.ceil(total / batchLimit) || 1;
      document.getElementById("batch-pagination-info").innerText = `Página ${pageNum} de ${totalPages} (${total} termos encontrados)`;
    }

    function playAudioUrl(url) {
      new Audio(url).play().catch(e => console.log("Áudio bloqueado:", e));
    }

    function setRowStatus(id, status, btnElement) {
      batchLocalStates[id] = status;
      const group = btnElement.parentElement;
      group.querySelectorAll(".pill-btn").forEach(b => {
        b.classList.remove("active-known", "active-unknown", "active-doubt");
      });
      if (status === "conhecido") btnElement.classList.add("active-known");
      if (status === "desconhecido") btnElement.classList.add("active-unknown");
      if (status === "duvida") btnElement.classList.add("active-doubt");
    }

    function batchMarkAllKnown() {
      markBatchRemainingAsKnown();
    }

    async function saveBatchEvaluations() {
      const itemsToSave = [];
      currentWords.forEach(item => {
        const st = batchLocalStates[item.id];
        if (st && st !== "pending") {
          itemsToSave.push({
            id: item.id,
            word: item.word,
            pos: item.pos,
            definition_en: item.definition_en,
            definition_pt: item.definition_pt,
            example_1: item.example_1,
            status: st
          });
        }
      });

      if (itemsToSave.length === 0) {
        showToast("Nenhuma alteração a salvar.");
        nextBatchPage();
        return;
      }

      showToast(`💾 Salvando ${itemsToSave.length} palavras do lote...`);

      const subdeckVal = document.getElementById("select-subdeck").value;
      try {
        const res = await fetch("/api/batch-evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: itemsToSave, subdeck: subdeckVal })
        });
        const data = await res.json();
        if (data && data.deck_stats) {
          currentDeckStats = data.deck_stats;
          updateDashboardStats(currentDeckStats);
        }
        fetchStatus();
        showToast(`✓ Salvas ${itemsToSave.length} palavras! Próximo lote carregado.`);
        nextBatchPage();
      } catch (err) {
        console.error("Erro ao salvar lote:", err);
        showToast("Erro ao salvar lote.", false);
      }
    }

    function nextBatchPage() {
      const statusFilter = document.getElementById("select-status").value;
      if (statusFilter === "pending") {
        currentBatchOffset = 0;
      } else {
        currentBatchOffset += batchLimit;
      }
      loadWords(currentBatchOffset);
    }

    function prevBatchPage() {
      if (currentBatchOffset >= batchLimit) {
        currentBatchOffset -= batchLimit;
        loadWords(currentBatchOffset);
      }
    }

    // ==========================================
    // RENDERIZAÇÃO DA FILA DE GAPS DO ANKI
    // ==========================================
    async function loadGapsView() {
      try {
        const res = await fetch("/api/gaps");
        const data = await res.json();
        const tbody = document.getElementById("gaps-table-body");
        tbody.innerHTML = "";

        if (document.getElementById("gaps-stat-ready")) {
          document.getElementById("gaps-stat-ready").innerText = data.ready_count || 0;
          document.getElementById("gaps-stat-waiting").innerText = data.waiting_count || 0;
          document.getElementById("gaps-stat-injected").innerText = data.injected_count || 0;
        }

        window.currentReadyGapsCount = data.ready_count || 0;
        updateInjectButtonLabel();

        const gapEl = document.getElementById("header-gap-count");
        if (gapEl) {
          gapEl.innerText = data.ready_count || 0;
          gapEl.style.display = (data.ready_count || 0) > 0 ? "inline-block" : "none";
        }

        if (!data.gaps || data.gaps.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 30px;">Nenhum gap registrado ainda. Continue triando no Modo Foco ou Grade!</td></tr>`;
          return;
        }

        data.gaps.forEach(g => {
          const tr = document.createElement("tr");

          const prioLabel = g.priority_label || (g.subdeck ? `★ Top ${g.subdeck.toUpperCase()}` : 'Top 01K');
          let prioStyle = "background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3);";
          if (g.subdeck === "01k" || g.importance_prio === 1) {
            prioStyle = "background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35);";
          } else if (g.subdeck === "02k" || g.importance_prio === 2) {
            prioStyle = "background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3);";
          }
          const prioBadge = `<span style="display:inline-block; padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; ${prioStyle}">${prioLabel}</span>`;

          let statusBadge = "";
          if (g.status_label === "injetado" || g.card_id) {
            statusBadge = `<span style="display:inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 700; font-size: 11px; border: 1px solid rgba(56, 189, 248, 0.3);">✓ Estudo Ativo</span>`;
          } else if (g.status_label === "pronto") {
            statusBadge = `<span style="display:inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(16, 185, 129, 0.15); color: #34d399; font-weight: 700; font-size: 11px; border: 1px solid rgba(16, 185, 129, 0.3);">🚀 Pronto p/ Injetar</span>`;
          } else {
            statusBadge = `<span style="display:inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-weight: 700; font-size: 11px; border: 1px solid rgba(245, 158, 11, 0.3);">⏳ Aguardando Frase i+1</span>`;
          }

          let typeBadge = "";
          if (g.status === "duvida") {
            typeBadge = `<span style="display:inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 6px; background: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 11px; font-weight: 600;">🟡 Dúvida</span>`;
          } else if (g.status === "desconhecido") {
            typeBadge = `<span style="display:inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 6px; background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 11px; font-weight: 600;">🔴 Não Sei</span>`;
          }

          const hasValidPhrase = g.has_sentence && g.frase;
          let iLevelBadge = "";
          if (g.is_strict_i1) {
            iLevelBadge = `<span style="display:inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 6px; background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 10px; font-weight: 700; border: 1px solid rgba(16, 185, 129, 0.35);">✓ i+1 Puro</span>`;
          } else if (g.extra_unknowns_count > 0) {
            const badWords = (g.extra_unknowns || []).slice(0, 3).join(", ");
            iLevelBadge = `<span style="display:inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 6px; background: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 10px; font-weight: 700; border: 1px solid rgba(239, 68, 68, 0.35);" title="Palavras desconhecidas extras: ${(g.extra_unknowns || []).join(', ')}">⚠️ ${g.i_level || 'i+2+'} (${badWords})</span>`;
          }

          const phraseHtml = hasValidPhrase 
            ? `<div><span style="font-style: italic; color: #e2e8f0;">"${g.frase}"</span>${iLevelBadge}</div>`
            : (g.frase 
                ? `<div><span style="font-style: italic; color: #94a3b8;">"${g.frase}"</span>${iLevelBadge}<div style="color: #f87171; font-size: 11px; margin-top: 3px;">⚠️ Não é i+1 puro (requer curadoria)</div></div>`
                : `<span style="font-style: italic; color: #64748b; font-size: 12px;">(Aguardando frase autêntica no acervo)</span>`);

          const defPtHtml = g.definicao_pt ? `<div style="color: #10b981; font-size: 12px; margin-top: 2px;">${formatDefinitionHtml(g.definicao_pt)}</div>` : "";
          const defHtml = g.has_def 
            ? `<div style="color: #f1f5f9;">${formatDefinitionHtml(g.definicao)}</div>${defPtHtml}`
            : `<div style="color: #fbbf24; font-style: italic; font-size: 13px;">(Aguardando definição pronta)</div>`;

          tr.innerHTML = `
            <td>${prioBadge}</td>
            <td><b style="color: #ffffff; font-family: var(--font-heading); font-size: 15px;">${g.termo_display || g.termo}</b>${typeBadge}</td>
            <td><span class="pos-badge">${g.pos || 'geral'}</span></td>
            <td>${defHtml}</td>
            <td>${phraseHtml}</td>
            <td>${statusBadge}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        console.error("Erro ao carregar gaps:", err);
      }
    }

    function updateInjectButtonLabel() {
      const sel = document.getElementById("select-inject-qty");
      const btn = document.getElementById("btn-inject-anki-view");
      if (!btn) return;
      const ready = window.currentReadyGapsCount || 0;
      btn.disabled = ready === 0;
      btn.style.opacity = ready === 0 ? "0.5" : "1";

      if (!sel) return;
      const val = sel.value;
      if (val === "all") {
        btn.innerHTML = `🚀 Injetar Todas as Prontas (${ready})`;
      } else {
        const qty = parseInt(val, 10);
        const toInject = Math.min(qty, ready);
        btn.innerHTML = `🚀 Injetar ${toInject > 0 ? toInject : qty} Mais Importantes`;
      }
    }

    async function enrichAllGaps() {
      const spinner = document.getElementById("enrich-spinner");
      if (spinner) spinner.style.display = "inline";
      showToast("🔍 Buscando frases e definições no acervo (Mairo Vergara e MWLD)...");

      try {
        const res = await fetch("/api/enrich-gaps", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.success) {
          showToast(`✓ ${data.message || 'Termos enriquecidos com sucesso!'}`);
          loadGapsView();
          fetchStatus();
        } else {
          showToast(`Erro ao enriquecer: ${data.error || 'Falha'}`, false);
        }
      } catch (err) {
        showToast("Erro na requisição de enriquecimento.", false);
      } finally {
        if (spinner) spinner.style.display = "none";
      }
    }

    async function syncWithCloud() {
      const btn = document.getElementById("btn-header-sync");
      const lbl = document.getElementById("sync-status-label");
      if (btn) btn.disabled = true;
      if (lbl) lbl.innerText = "...";
      showToast("Sincronizando mapa de vocabulario com Google Cloud Run...");
      try {
        const res = await fetch("/api/sync-cloud", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message || "Sincronizacao concluida com sucesso!");
          await fetchStatus();
          if (document.getElementById("view-gaps") && document.getElementById("view-gaps").style.display !== "none") {
            loadGapsView();
          } else {
            loadWords(currentBatchOffset);
          }
        } else {
          showToast(data.message || "Erro ao sincronizar com a nuvem.", false);
        }
      } catch (err) {
        showToast("Falha de rede ao sincronizar com a nuvem.", false);
      } finally {
        if (btn) btn.disabled = false;
        if (lbl) lbl.innerText = "Nuvem";
      }
    }

    // ==========================================
    // INJEÇÃO NO ANKI & SINCRONIZAÇÃO
    // ==========================================
    async function injectSelectedGapsToAnki() {
      const btnView = document.getElementById("btn-inject-anki-view");
      const sel = document.getElementById("select-inject-qty");
      const qty = sel ? sel.value : "10";

      if (btnView) { btnView.disabled = true; btnView.style.opacity = "0.6"; }
      showToast(`🚀 Injetando as palavras mais importantes no Anki e baixando áudios...`);

      try {
        const res = await fetch("/api/inject-anki", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ limit: qty })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`🎉 ${data.message || 'Cartas injetadas e sincronizadas!'}`);
          fetchStatus();
          loadGapsView();
        } else {
          showToast(data.message || data.error || 'Falha ao injetar no Anki', false);
        }
      } catch (err) {
        showToast("Erro ao conectar com o AnkiConnect.", false);
      } finally {
        if (btnView) { btnView.disabled = false; btnView.style.opacity = "1"; }
        updateInjectButtonLabel();
      }
    }

    function injectAllGapsToAnki() {
      return injectSelectedGapsToAnki();
    }

    // ==========================================
    // CONTROLE DE TELAS (SWITCH VIEW)
    // ==========================================
    
    // ==========================================
    // LEXIS SUITE - MODULES & LISTENING STUDIO LOGIC
    // ==========================================
    

    // ==========================================
    // LEXIS SUITE - MODULES & LISTENING STUDIO LOGIC (IMAGE 1 REPLICA)
    // ==========================================
    const moduleNamesMap = {
      vocab: { name: "Vocabulário", sub: "/ Triagem & Chunks", color: "var(--cyan)" },
      listening: { name: "Listening Studio", sub: "/ Escuta às Cegas", color: "var(--purple)" },
      anki: { name: "Anki Hub", sub: "/ Fila & Injeção", color: "var(--amber)" },
      analytics: { name: "Analytics", sub: "/ Métricas CEFR", color: "var(--blue)" }
    };

    function switchModule(moduleName) {
      const target = document.getElementById('view-module-' + moduleName);
      if (!target) return;
      pauseListeningMedia();
      document.querySelectorAll('.module-view').forEach(view => {
        const active = view === target;
        view.style.display = active ? 'block' : 'none';
        view.classList.toggle('active', active);
      });
      document.querySelectorAll('.topbar .tab, .bottom-nav .tab').forEach(btn => {
        const active = btn.dataset.module === moduleName;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-current', active ? 'page' : 'false');
      });
      const info = moduleNamesMap[moduleName];
      const crumbMod = document.getElementById('breadcrumb-module-name');
      const crumbSub = document.getElementById('breadcrumb-subview');
      if (crumbMod && info) { crumbMod.textContent = info.name; crumbMod.style.color = info.color; }
      if (crumbSub && info) {
        const subMap = { video: '/ Vídeo Ditado', audio: '/ Escuta às Cegas', podcast: '/ Imersão Contínua' };
        crumbSub.textContent = moduleName === 'listening' ? (subMap[selectedListeningSubmode] || '/ Listening') : info.sub;
      }
      if (moduleName === 'listening') {
        if (selectedListeningSubmode === 'video') {
          initYouTubePlayer();
          renderWordSlots(getCleanTargetTokens(document.getElementById('dictation-input').value));
        } else if (selectedListeningSubmode === 'podcast' && !podcastTracks.length) {
          loadImmersionPlaylist();
        }
      } else if (moduleName === 'anki') {
        loadAnkiHubModule();
      } else if (moduleName === 'analytics') {
        loadAnalyticsModule();
      }
    }

    // Listening uses real local media; no synthesized placeholder sound.
    const LISTENING_STORAGE = 'lexis_listening_v2';
    function readListeningStore(key, fallback) {
      try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (_) { return fallback; }
    }
    function writeListeningStore(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); return true; }
      catch (_) { showToast('Não foi possível salvar neste navegador. Mantenha esta aba aberta.', false); return false; }
    }
    const listeningSessions = readListeningStore(LISTENING_STORAGE, {});
    const pendingListening = readListeningStore(LISTENING_STORAGE + '_pending', {});
    const sentListening = readListeningStore(LISTENING_STORAGE + '_sent', {});
    const listeningSends = new Map();
    let audioTracks = [], audioTrackIndex = 0, audioObjectURL = null, localObjectURL = null;
    let listeningRate = 1, currentDictationSpeed = 1;
    let currentSegmentIndex = 0, ytPlayer = null, ytReady = false, ytLoading = false;
    let youtubeLoadTimeout = null;
    let videoTimeCheckInterval = null, segmentUnlocked = false, segmentAssisted = false;
    let selectedListeningSubmode = 'video', localVideoData = null, selectedYoutubeData = null;
    let localMediaIdentity = '', currentSourceKey = '', sessionCompleted = false;
    const VIDEO_PRESETS = {
      jobs: { sessionId: 'preset:jobs', legacySessionKey: 'f3ccabbf', videoId: 'UF8uR6Z6KLc', title: 'Steve Jobs · Discurso Stanford', segments: [
        { start: 25.8, end: 30.1, en: 'I am honored to be with you today for your commencement.', pt: 'Sinto-me honrado por estar com vocês hoje na sua formatura.' },
        { start: 30.1, end: 35.2, en: 'from one of the finest universities in the world.', pt: 'em uma das melhores universidades do mundo.' },
        { start: 37.3, end: 41.2, en: 'I never graduated from college.', pt: 'Eu nunca me formei na faculdade.' }
      ] }
    };
    let activeVideoData = structuredClone(VIDEO_PRESETS.jobs);
    selectedYoutubeData = activeVideoData;
    function listeningHash(text) {
      let hash = 2166136261;
      for (const char of text) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
      return (hash >>> 0).toString(16);
    }
    function mediaIdentity(file) { return [file.name, file.size, file.lastModified].join(':'); }
    function sourceKey(data) {
      if (data.sessionId) return data.sessionId;
      return listeningHash(JSON.stringify([data.videoId || data.identity || data.title, data.segments]));
    }
    function currentSegment() { return activeVideoData.segments[currentSegmentIndex]; }
    const dictationTimingOverrides = readListeningStore(LISTENING_STORAGE + '_timings', {});
    function currentSegmentTiming() {
      const segment = currentSegment();
      if (!segment) return null;
      const override = (dictationTimingOverrides[currentSourceKey] || {})[currentSegmentIndex];
      return override && Number.isFinite(override.start) && Number.isFinite(override.end) && override.start >= 0 && override.end > override.start ? override : { start: segment.start, end: segment.end };
    }
    function updateDictationTimingLabels() {
      const timing = currentSegmentTiming();
      const start = document.getElementById('dictation-start-time');
      const end = document.getElementById('dictation-end-time');
      start.disabled = end.disabled = !timing;
      if (!timing) { start.value = ''; end.value = ''; return; }
      start.value = timing.start.toFixed(2);
      end.value = timing.end.toFixed(2);
      document.getElementById('dictation-time-label').textContent = 'Trecho: ' + formatTime(timing.start) + ' – ' + formatTime(timing.end);
    }
    function saveDictationTiming(start, end) {
      if (!currentSegment() || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) {
        showToast('Informe um início válido e um fim maior que o início.', false); return false;
      }
      const duration = VideoController.isLocal ? document.getElementById('local-video-player').duration : ytReady && ytPlayer.getDuration ? ytPlayer.getDuration() : NaN;
      if (Number.isFinite(duration) && duration > 0 && end > duration) {
        showToast('O fim do trecho ultrapassa a duração do vídeo.', false); return false;
      }
      dictationTimingOverrides[currentSourceKey] = dictationTimingOverrides[currentSourceKey] || {};
      dictationTimingOverrides[currentSourceKey][currentSegmentIndex] = { start, end };
      writeListeningStore(LISTENING_STORAGE + '_timings', dictationTimingOverrides);
      updateDictationTimingLabels();
      return true;
    }
    function applyDictationTiming() {
      const startText = document.getElementById('dictation-start-time').value;
      const endText = document.getElementById('dictation-end-time').value;
      if (!startText || !endText) return showToast('Preencha os dois tempos em segundos.', false);
      if (saveDictationTiming(Number(startText), Number(endText))) {
        stopVideoWatcher(); VideoController.pause();
        showToast('Limites ajustados. Sua resposta foi mantida; repita o trecho para conferir.');
      }
    }
    function resetDictationTiming() {
      if (!currentSegment()) return;
      if (dictationTimingOverrides[currentSourceKey]) delete dictationTimingOverrides[currentSourceKey][currentSegmentIndex];
      writeListeningStore(LISTENING_STORAGE + '_timings', dictationTimingOverrides);
      stopVideoWatcher(); VideoController.pause(); updateDictationTimingLabels();
    }
    function extendDictationSegment() {
      const timing = currentSegmentTiming();
      if (!timing) return;
      const duration = VideoController.isLocal ? document.getElementById('local-video-player').duration : ytReady && ytPlayer.getDuration ? ytPlayer.getDuration() : NaN;
      const end = Number.isFinite(duration) && duration > 0 ? Math.min(duration, timing.end + 2) : timing.end + 2;
      if (end <= timing.end) return showToast('Este trecho já chega ao fim do vídeo.', false);
      if (!saveDictationTiming(timing.start, end)) return;
      // Continue from the prior boundary, with a small overlap, without resetting the answer.
      VideoController.seekTo(Math.max(timing.start, timing.end - .3), true);
      startVideoWatcher(); focusDictationInput();
    }
    function isListeningVisible() { return document.getElementById('view-module-listening').classList.contains('active'); }
    function pauseListeningMedia() {
      stopVideoWatcher();
      const local = document.getElementById('local-video-player');
      if (local) local.pause();
      if (ytReady && ytPlayer && ytPlayer.pauseVideo) ytPlayer.pauseVideo();
      stopListeningAudio();
      stopPodcastPlayback();
      if (currentSourceKey) persistDictationSession();
    }
    const VideoController = {
      isLocal: false,
      play() {
        if (!isListeningVisible() || selectedListeningSubmode !== 'video') return;
        if (this.isLocal) {
          const video = document.getElementById('local-video-player');
          if (!video.src) return showToast('Escolha primeiro o vídeo local.', false);
          video.playbackRate = currentDictationSpeed;
          video.play().catch(() => { stopVideoWatcher(); showToast('Não foi possível reproduzir. Verifique o formato do arquivo.', false); });
        } else if (ytReady) {
          ytPlayer.setPlaybackRate(currentDictationSpeed);
          ytPlayer.playVideo();
        } else showToast('O player ainda está carregando. Tente novamente em instantes.', false);
      },
      pause() {
        if (this.isLocal) document.getElementById('local-video-player').pause();
        else if (ytReady) ytPlayer.pauseVideo();
      },
      seekTo(seconds, andPlay = false) {
        if (this.isLocal) {
          const video = document.getElementById('local-video-player');
          if (!video.src || video.readyState < 1) return;
          video.currentTime = Math.max(0, Math.min(seconds, Number.isFinite(video.duration) ? video.duration : seconds));
        } else if (ytReady) ytPlayer.seekTo(Math.max(0, seconds), true);
        if (!andPlay) this.pause();
        if (andPlay) this.play();
      },
      getCurrentTime() {
        return this.isLocal ? document.getElementById('local-video-player').currentTime : (ytReady ? ytPlayer.getCurrentTime() : 0);
      },
      setSpeed(speed) {
        currentDictationSpeed = speed;
        if (this.isLocal) document.getElementById('local-video-player').playbackRate = speed;
        else if (ytReady) ytPlayer.setPlaybackRate(speed);
        document.getElementById('dictation-speed-toggle').textContent = speed + '×';
      }
    };
    function toggleDictationSpeed() {
      let speeds = [1, .75, .5];
      if (!VideoController.isLocal && ytReady && ytPlayer.getAvailablePlaybackRates) {
        const available = ytPlayer.getAvailablePlaybackRates();
        speeds = speeds.filter(speed => available.includes(speed));
      }
      if (!speeds.length) speeds = [1];
      VideoController.setSpeed(speeds[(speeds.indexOf(currentDictationSpeed) + 1) % speeds.length]);
    }
    function switchListeningSubmode(submode) {
      if (!['video', 'audio', 'podcast'].includes(submode)) return;
      pauseListeningMedia();
      selectedListeningSubmode = submode;
      document.getElementById('submode-video-container').style.display = submode === 'video' ? 'block' : 'none';
      document.getElementById('submode-audio-container').style.display = submode === 'audio' ? 'grid' : 'none';
      const podContainer = document.getElementById('submode-podcast-container');
      if (podContainer) podContainer.style.display = submode === 'podcast' ? 'grid' : 'none';
      for (const mode of ['video', 'audio', 'podcast']) {
        const btn = document.getElementById('btn-mode-' + mode);
        if (!btn) continue;
        btn.classList.toggle('active', mode === submode);
        btn.setAttribute('aria-pressed', String(mode === submode));
      }
      const titles = {
        video: 'Vídeo Ditado Interativo',
        audio: 'Escuta às Cegas',
        podcast: 'Playlist Contínua de Imersão'
      };
      const crumbs = {
        video: '/ Vídeo Ditado',
        audio: '/ Escuta às Cegas',
        podcast: '/ Imersão Contínua'
      };
      const descs = {
        video: 'Ouça o trecho, escreva sua hipótese e compare. Use pistas quando precisar.',
        audio: 'Escolha um áudio real e, se quiser, importe a transcrição para treinar por trechos.',
        podcast: 'Podcast pessoal contínuo com repetição reflexiva (1x -> Pausa -> 2x) e controle na tela de bloqueio.'
      };
      document.querySelector('.listening-title-row h2').textContent = titles[submode];
      if (isListeningVisible()) document.getElementById('breadcrumb-subview').textContent = crumbs[submode];
      document.getElementById('listening-submode-desc').textContent = descs[submode];
      if (submode === 'podcast' && !podcastTracks.length) {
        loadImmersionPlaylist();
      }
    }
    function switchVideoSource(source) {
      if (!['local', 'youtube'].includes(source)) return;
      pauseListeningMedia();
      const local = source === 'local';
      VideoController.isLocal = local;
      document.getElementById('btn-src-yt').classList.toggle('active', !local);
      document.getElementById('btn-src-local').classList.toggle('active', local);
      document.getElementById('yt-controls-wrap').style.display = local ? 'none' : 'flex';
      document.getElementById('local-controls-wrap').style.display = local ? 'flex' : 'none';
      document.getElementById('yt-player-frame').style.display = local ? 'none' : 'block';
      document.getElementById('local-video-player').style.display = local ? 'block' : 'none';
      document.getElementById('listening-player-status').textContent = '';
      activeVideoData = local ? (localVideoData || { title: 'Vídeo local', segments: [] }) : selectedYoutubeData;
      activateDictationData();
      if (!local) initYouTubePlayer();
    }
    function onLocalVideoSelected(event) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      pauseListeningMedia();
      const video = document.getElementById('local-video-player');
      if (localObjectURL) URL.revokeObjectURL(localObjectURL);
      localObjectURL = URL.createObjectURL(file);
      localMediaIdentity = mediaIdentity(file);
      localVideoData = { title: file.name, identity: localMediaIdentity, isLocal: true, segments: [] };
      activeVideoData = localVideoData;
      video.src = localObjectURL;
      video.onplay = startVideoWatcher;
      video.onpause = stopVideoWatcher;
      video.onended = stopVideoWatcher;
      video.onerror = () => showToast('Não foi possível abrir o vídeo. Tente MP4 (H.264) ou WebM.', false);
      video.onloadedmetadata = () => {
        if (VideoController.isLocal && currentSegmentTiming()) VideoController.seekTo(currentSegmentTiming().start);
      };
      video.load();
      activateDictationData();
      document.getElementById('local-file-status').textContent = 'Vídeo: ' + file.name + ' · Importe a legenda correspondente.';
    }
    function parseTimeStr(text) {
      const parts = String(text || '').trim().replace(',', '.').split(':').map(Number);
      if (!parts.length || parts.length > 3 || parts.some(n => !Number.isFinite(n) || n < 0)) return NaN;
      return parts.reduce((seconds, part) => seconds * 60 + part, 0);
    }
    function parseSRTorVTT(text) {
      const blocks = String(text || '').replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split(/\n\s*\n/);
      const segments = [];
      const timestamp = /((?:\d{1,}:)?\d{2}:\d{2}[,.]\d{3})\s*-->\s*((?:\d{1,}:)?\d{2}:\d{2}[,.]\d{3})/;
      for (const block of blocks) {
        const lines = block.trim().split('\n');
        if (/^(NOTE|STYLE|REGION)(\s|$)/.test(lines[0])) continue;
        const i = lines.findIndex(line => timestamp.test(line));
        if (i < 0) continue;
        const match = lines[i].match(timestamp);
        const start = parseTimeStr(match[1]), end = parseTimeStr(match[2]);
        const en = lines.slice(i + 1).join(' ').replace(/<[^>]*>/g, '').replace(/\{\\[^}]*\}/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').trim();
        if (Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end > start && en) segments.push({ start, end, en, pt: '' });
      }
      return segments.sort((a, b) => a.start - b.start);
    }
    async function importListeningCaptions(event, source) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      const data = source === 'local' ? localVideoData : selectedYoutubeData;
      const audioAtStart = audioObjectURL;
      if (source !== 'audio' && !data) return showToast('Escolha primeiro o vídeo.', false);
      if (source === 'audio' && !audioObjectURL) return showToast('Escolha primeiro o áudio.', false);
      try {
        let segments = parseSRTorVTT(await file.text());
        const media = source === 'audio' ? listeningAudio() : source === 'local' ? document.getElementById('local-video-player') : null;
        if (media && Number.isFinite(media.duration)) segments = segments.filter(seg => seg.end <= media.duration + .1);
        if (!segments.length) throw Error('A legenda não contém trechos válidos.');
        if (source === 'audio') {
          if (audioAtStart !== audioObjectURL) return;
          audioTracks = segments;
          audioTrackIndex = 0;
          stopListeningAudio();
          selectListeningTrack(0);
        } else {
          if (data !== (source === 'local' ? localVideoData : selectedYoutubeData)) return;
          data.segments = segments;
          delete data.sessionId; delete data.legacySessionKey;
          if (VideoController.isLocal === (source === 'local')) {
            pauseListeningMedia();
            activeVideoData = data;
            activateDictationData();
          }
        }
        showToast(segments.length + ' trechos importados. Confira a sincronização com seu arquivo.');
      } catch (error) { showToast(error.message || 'Não foi possível ler a legenda.', false); }
    }
    function onLocalSrtSelected(event) { return importListeningCaptions(event, 'local'); }
    function onYoutubeSrtSelected(event) { return importListeningCaptions(event, 'youtube'); }
    function onListeningCaptionsSelected(event) { return importListeningCaptions(event, 'audio'); }
    function initYouTubePlayer() {
      if (ytPlayer || ytLoading || VideoController.isLocal) return;
      if (window.YT && window.YT.Player) return setupYTInstance();
      ytLoading = true;
      document.getElementById('listening-player-status').textContent = 'Carregando player do YouTube…';
      clearTimeout(youtubeLoadTimeout);
      youtubeLoadTimeout = setTimeout(() => {
        if (!ytReady && !VideoController.isLocal) document.getElementById('listening-player-status').textContent = 'O YouTube está demorando para responder. Verifique a conexão ou use um vídeo local.';
      }, 12000);
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      tag.id = 'lexis-youtube-api';
      tag.onerror = () => { ytLoading = false; clearTimeout(youtubeLoadTimeout); tag.remove(); document.getElementById('listening-player-status').textContent = 'YouTube indisponível. Use um vídeo local ou entre novamente no módulo para tentar outra vez.'; };
      window.onYouTubeIframeAPIReady = () => { ytLoading = false; if (!VideoController.isLocal) setupYTInstance(); };
      document.head.appendChild(tag);
    }
    function setupYTInstance() {
      if (ytPlayer) return;
      ytPlayer = new YT.Player('yt-player-frame', {
        height: '100%', width: '100%', videoId: selectedYoutubeData.videoId,
        playerVars: { autoplay: 0, controls: 1, rel: 0, cc_load_policy: 0, playsinline: 1, origin: location.origin },
        events: { onReady: onPlayerReady, onStateChange: onPlayerStateChange,
          onPlaybackRateChange: event => { currentDictationSpeed = event.data; document.getElementById('dictation-speed-toggle').textContent = event.data + '×'; },
          onError: () => { stopVideoWatcher(); document.getElementById('listening-player-status').textContent = 'O YouTube não conseguiu abrir este vídeo. Verifique o link e a permissão de reprodução ou escolha outro vídeo.'; } }
      });
    }
    async function fetchYoutubeTranscript(videoId) {
      if (!videoId) return false;
      const statusEl = document.getElementById('listening-player-status');
      if (statusEl) statusEl.textContent = 'Carregando frases completas do YouTube...';
      try {
        const resp = await fetch('/api/youtube-transcript?v=' + encodeURIComponent(videoId));
        const data = await resp.json();
        if (data && data.success && data.segments && data.segments.length > 0) {
          activeVideoData.segments = data.segments;
          if (selectedYoutubeData) selectedYoutubeData.segments = data.segments;
          if (statusEl) statusEl.textContent = '';
          activateDictationData();
          showToast(`Sucesso! ${data.total} frases carregadas do vídeo.`);
          return true;
        } else if (statusEl) {
          statusEl.textContent = data.error || '';
        }
      } catch (err) {
        if (statusEl) statusEl.textContent = '';
      }
      return false;
    }

    function prevDictationSegment() {
      if (!activeVideoData || !activeVideoData.segments || activeVideoData.segments.length === 0) return;
      if (currentSegmentIndex > 0) {
        loadSegment(currentSegmentIndex - 1);
      } else {
        showToast('Você já está na primeira frase.');
      }
    }

    function skipToNextSegment() {
      if (!activeVideoData || !activeVideoData.segments || activeVideoData.segments.length === 0) return;
      if (currentSegmentIndex < activeVideoData.segments.length - 1) {
        loadSegment(currentSegmentIndex + 1);
      } else {
        showToast('Você está na última frase do vídeo.');
      }
    }
    function onPlayerReady() {
      ytReady = true;
      clearTimeout(youtubeLoadTimeout);
      document.getElementById('listening-player-status').textContent = '';
      if (VideoController.isLocal) { ytPlayer.pauseVideo(); return; }
      ytPlayer.cueVideoById(selectedYoutubeData.videoId, currentSegmentTiming() ? currentSegmentTiming().start : 0);
      if (selectedYoutubeData && selectedYoutubeData.videoId) {
        fetchYoutubeTranscript(selectedYoutubeData.videoId);
      }
    }
    function onPlayerStateChange(event) {
      if (VideoController.isLocal) return;
      if (event.data === YT.PlayerState.PLAYING) {
        if (!isListeningVisible() || selectedListeningSubmode !== 'video') { ytPlayer.pauseVideo(); return; }
        startVideoWatcher();
      } else stopVideoWatcher();
    }
    function startVideoWatcher() {
      stopVideoWatcher();
      if (!currentSegment()) return;
      videoTimeCheckInterval = setInterval(() => {
        const seg = currentSegmentTiming();
        if (!isListeningVisible() || selectedListeningSubmode !== 'video') return pauseListeningMedia();
        if (seg && VideoController.getCurrentTime() >= seg.end) {
          stopVideoWatcher();
          VideoController.pause();
          VideoController.seekTo(seg.end, false);
          focusDictationInput();
        }
      }, 50);
    }
    function stopVideoWatcher() { clearInterval(videoTimeCheckInterval); videoTimeCheckInterval = null; }
    function activateDictationData() {
      currentSourceKey = sourceKey(activeVideoData);
      if (!listeningSessions[currentSourceKey] && activeVideoData.legacySessionKey && listeningSessions[activeVideoData.legacySessionKey]) {
        listeningSessions[currentSourceKey] = structuredClone(listeningSessions[activeVideoData.legacySessionKey]);
        writeListeningStore(LISTENING_STORAGE, listeningSessions);
      }
      const stored = listeningSessions[currentSourceKey];
      currentSegmentIndex = stored && Number.isInteger(stored.index) ? Math.max(0, Math.min(stored.index, activeVideoData.segments.length - 1)) : 0;
      sessionCompleted = Boolean(stored && stored.completed);
      loadSegment(currentSegmentIndex, false, true);
      if (sessionCompleted) showDictationSummary();
    }
    function persistDictationSession() {
      if (!currentSourceKey || !currentSegment()) return;
      const session = listeningSessions[currentSourceKey] || { outcomes: {} };
      session.outcomes = session.outcomes || {};
      Object.assign(session, { index: currentSegmentIndex, input: document.getElementById('dictation-input').value, assisted: segmentAssisted, unlocked: segmentUnlocked, completed: sessionCompleted });
      listeningSessions[currentSourceKey] = session;
      writeListeningStore(LISTENING_STORAGE, listeningSessions);
    }
    function loadSegment(index, andPlay = true, restore = false) {
      stopVideoWatcher();
      const seg = activeVideoData.segments[index];
      currentSegmentIndex = seg ? index : 0;
      segmentUnlocked = false; segmentAssisted = false;
      const input = document.getElementById('dictation-input');
      input.value = ''; input.disabled = !seg; input.readOnly = false; input.className = 'dictation-input-field';
      document.getElementById('spelling-hint-box').style.display = 'none';
      document.getElementById('dictation-success-box').style.display = 'none';
      document.getElementById('dictation-summary').hidden = true;
      document.getElementById('dictation-segment-label').textContent = seg ? 'FRASE ' + (index + 1) + ' / ' + activeVideoData.segments.length : 'SEM LEGENDA';
      document.getElementById('dictation-time-label').textContent = seg ? 'Trecho: ' + formatTime(seg.start) + ' – ' + formatTime(seg.end) : 'Importe uma legenda sincronizada para começar.';
      for (const btn of document.querySelectorAll('#submode-video-container .dictation-actions-row button')) btn.disabled = !seg;
      document.getElementById('dictation-next-btn').textContent = index === activeVideoData.segments.length - 1 ? 'Concluir treino (Enter)' : 'Próxima frase (Enter)';
      updateDictationTimingLabels();
      if (!seg) { document.getElementById('dictation-word-slots').replaceChildren(); updateDictationStatus(); return; }
      const stored = restore && listeningSessions[currentSourceKey];
      if (stored) { input.value = stored.input || ''; segmentAssisted = Boolean(stored.assisted); }
      renderWordSlots(getCleanTargetTokens(input.value));
      if (stored && stored.unlocked && stored.outcomes && stored.outcomes[index]) handleSegmentSuccess(seg, stored.outcomes[index], true);
      VideoController.seekTo(currentSegmentTiming().start, andPlay);
      if (andPlay) { startVideoWatcher(); focusDictationInput(); }
      updateDictationStatus(); persistDictationSession();
    }
    function replayCurrentSegment() {
      const seg = currentSegment();
      if (!seg) return showToast('Importe uma legenda para treinar por trecho.', false);
      VideoController.seekTo(currentSegmentTiming().start, true); startVideoWatcher(); focusDictationInput();
    }
    function focusDictationInput() {
      if (isListeningVisible() && selectedListeningSubmode === 'video') document.getElementById('dictation-input').focus({ preventScroll: true });
    }
    function formatTime(seconds) {
      seconds = Math.max(0, Number(seconds) || 0);
      const totalMs = Math.round(seconds * 1000);
      return String(Math.floor(totalMs / 60000)).padStart(2, '0') + ':' + String(Math.floor(totalMs / 1000) % 60).padStart(2, '0') + '.' + String(totalMs % 1000).padStart(3, '0');
    }
    function normalizeDictationText(text) {
      return String(text || '').toLowerCase().replace(/[’‘]/g, "'").replace(/[^\p{L}\p{N}'\s]/gu, ' ').replace(/\s+/g, ' ').trim();
    }
    const CONTRACTION_MAP = {
      "don't": 'do not', dont: 'do not', "can't": 'cannot', cant: 'cannot', "won't": 'will not', wont: 'will not',
      "i'm": 'i am', im: 'i am', "you're": 'you are', youre: 'you are', "they're": 'they are', theyre: 'they are', "we're": 'we are',
      "isn't": 'is not', isnt: 'is not', "aren't": 'are not', arent: 'are not', "didn't": 'did not', didnt: 'did not',
      "doesn't": 'does not', doesnt: 'does not', "couldn't": 'could not', couldnt: 'could not', "wouldn't": 'would not', wouldnt: 'would not',
      "shouldn't": 'should not', shouldnt: 'should not', "i've": 'i have', ive: 'i have', "you've": 'you have', youve: 'you have',
      "they've": 'they have', theyve: 'they have', "we've": 'we have', weve: 'we have', "he's": 'he is', "she's": 'she is',
      "it's": 'it is', "there's": 'there is', "that's": 'that is', gonna: 'going to', wanna: 'want to', gotta: 'got to',
      "i'll": 'i will', "you'll": 'you will', "we'll": 'we will', "they'll": 'they will', "he'll": 'he will', "she'll": 'she will', "it'll": 'it will',
      "i'd": 'i would', "you'd": 'you would', "we'd": 'we would', "they'd": 'they would', "he'd": 'he would', "she'd": 'she would', "it'd": 'it would'
    };
    function expandContractions(text) {
      return text.split(' ').map(word => CONTRACTION_MAP[word] || word).join(' ').replace(/\bcan not\b/g, 'cannot');
    }
    function getCleanTargetTokens(text) { return expandContractions(normalizeDictationText(text)).split(' ').filter(Boolean); }
    function dictationTokenVariants(text) {
      let variants = [[]];
      for (const word of normalizeDictationText(text).split(' ').filter(Boolean)) {
        const ambiguous = word.match(/^(he|she|it|there|that)'s$|^(i|you|we|they|he|she|it)'d$/);
        const choices = ambiguous ? (ambiguous[1] ? [ambiguous[1] + ' is', ambiguous[1] + ' has'] : [ambiguous[2] + ' would', ambiguous[2] + ' had']) : [expandContractions(word)];
        variants = variants.flatMap(tokens => choices.map(choice => [...tokens, ...choice.split(' ')])).slice(0, 64);
      }
      return variants;
    }
    function alignDictationTokens(value, reference) {
      let best = null, bestScore = Infinity;
      for (const user of dictationTokenVariants(value)) for (const target of dictationTokenVariants(reference)) {
        const score = user.reduce((sum, word, i) => sum + (word === target[i] ? 0 : 1), 0) + Math.abs(target.length - user.length);
        if (score < bestScore) { best = { user, target }; bestScore = score; }
        if (score === 0) return best;
      }
      return best || { user: [], target: [] };
    }
    function calcLevenshtein(a, b) {
      let row = Array.from({ length: b.length + 1 }, (_, i) => i);
      for (let i = 1; i <= a.length; i++) {
        const next = [i];
        for (let j = 1; j <= b.length; j++) next[j] = Math.min(next[j - 1] + 1, row[j] + 1, row[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        row = next;
      }
      return row[b.length];
    }
    function renderWordSlots(userTokens = [], activeTypo = null, targetOverride = null) {
      const container = document.getElementById('dictation-word-slots');
      container.replaceChildren();
      const seg = currentSegment();
      if (!seg) return false;
      const targets = targetOverride || getCleanTargetTokens(seg.en);
      targets.forEach((word, index) => {
        const span = document.createElement('span');
        const matched = userTokens[index] === word;
        span.className = 'word-slot ' + (matched ? 'completed' : userTokens[index] ? 'typo' : index === userTokens.length ? 'current' : 'pending');
        span.textContent = matched ? '✓ ' + word : userTokens[index] ? userTokens[index] : '_'.repeat(Math.max(2, Math.min(word.length, 18)));
        if (!matched && userTokens[index]) span.title = 'Palavra a conferir';
        container.appendChild(span);
      });
      if (userTokens.length > targets.length) {
        const extra = document.createElement('span'); extra.className = 'word-slot typo'; extra.textContent = 'Palavras extras: ' + userTokens.slice(targets.length).join(' '); container.appendChild(extra);
      }
      return targets.length > 0 && targets.length === userTokens.length && targets.every((word, i) => userTokens[i] === word);
    }
    function onDictationInput(value) {
      const seg = currentSegment();
      if (!seg || segmentUnlocked) return;
      const { user, target } = alignDictationTokens(value, seg.en);
      const matched = renderWordSlots(user, null, target);
      const input = document.getElementById('dictation-input');
      const hint = document.getElementById('spelling-hint-box'); hint.style.display = 'none';
      input.className = 'dictation-input-field';
      // Avoid giving away a word while the learner is still typing its prefix.
      const mismatch = user.findIndex((word, i) => word !== target[i]);
      if (mismatch >= 0 && target[mismatch]) {
        const word = user[mismatch], expected = target[mismatch];
        const finished = mismatch < user.length - 1 || /\s$/.test(value);
        if (finished && word.length >= 3 && expected.length >= 3 && calcLevenshtein(word, expected) <= 2) {
          document.getElementById('spelling-hint-text').textContent = 'Confira a ortografia da palavra ' + (mismatch + 1) + '. Use uma pista se precisar.';
          input.classList.add('almost'); hint.style.display = 'flex';
        }
      }
      if (matched) handleSegmentSuccess(seg, segmentAssisted ? 'assisted' : 'correct');
      persistDictationSession();
    }
    function handleSegmentSuccess(seg, outcome = 'correct', restoring = false) {
      segmentUnlocked = true;
      document.getElementById('dictation-input').className = 'dictation-input-field correct';
      document.getElementById('dictation-input').readOnly = true;
      document.getElementById('spelling-hint-box').style.display = 'none';
      document.getElementById('dictation-result-label').textContent = outcome === 'revealed' ? 'Frase revelada · ouça novamente e compare' : outcome === 'assisted' ? 'Concluída com ajuda' : 'Acertou sem pistas!';
      document.getElementById('dictation-revealed-en').textContent = seg.en;
      document.getElementById('dictation-revealed-pt').textContent = seg.pt || 'Tradução não fornecida para este trecho.';
      document.getElementById('dictation-success-box').style.display = 'flex';
      const session = listeningSessions[currentSourceKey] || { outcomes: {} };
      session.outcomes = session.outcomes || {}; session.outcomes[currentSegmentIndex] = outcome;
      listeningSessions[currentSourceKey] = session;
      updateDictationStatus();
      if (!restoring) persistDictationSession();
    }
    function nextDictationSegment() {
      if (!segmentUnlocked) return;
      document.getElementById('dictation-input').readOnly = false;
      if (currentSegmentIndex < activeVideoData.segments.length - 1) loadSegment(currentSegmentIndex + 1);
      else { sessionCompleted = true; VideoController.pause(); stopVideoWatcher(); persistDictationSession(); showDictationSummary(); }
    }
    function updateDictationStatus() {
      const outcomes = (listeningSessions[currentSourceKey] || {}).outcomes || {};
      const completed = Object.keys(outcomes).length;
      document.getElementById('dictation-session-status').textContent = activeVideoData.segments.length
        ? completed + ' / ' + activeVideoData.segments.length + ' trechos conferidos · salvo neste navegador'
        : 'Sem transcrição. Importe SRT/VTT correspondente ao vídeo; o app não inventa as falas.';
      document.getElementById('dictation-save-btn').disabled = !currentSegment();
    }
    function showDictationSummary() {
      const outcomes = Object.values((listeningSessions[currentSourceKey] || {}).outcomes || {});
      const summary = document.getElementById('dictation-summary');
      summary.hidden = false;
      summary.textContent = 'Treino concluído. Sem pistas: ' + outcomes.filter(x => x === 'correct').length + ' · Com ajuda: ' + outcomes.filter(x => x === 'assisted').length + ' · Reveladas: ' + outcomes.filter(x => x === 'revealed').length + '. Use “Recomeçar treino” para repetir.';
    }
    function restartDictationSession() {
      if (!currentSegment()) return;
      pauseListeningMedia();
      delete listeningSessions[currentSourceKey]; sessionCompleted = false;
      document.getElementById('dictation-input').readOnly = false;
      loadSegment(0, false);
    }
    function onDictationKey(event) {
      if (event.isComposing) return;
      if (event.altKey && event.key.toLowerCase() === 'r') { event.preventDefault(); replayCurrentSegment(); }
      else if (event.altKey && event.key.toLowerCase() === 'h') { event.preventDefault(); showNextWordHint(); }
      else if (event.key === 'Enter' && segmentUnlocked) { event.preventDefault(); nextDictationSegment(); }
    }
    function showNextWordHint() {
      const seg = currentSegment();
      if (!seg || segmentUnlocked) return;
      const input = document.getElementById('dictation-input');
      const { user, target } = alignDictationTokens(input.value, seg.en);
      let index = 0;
      while (index < target.length && user[index] === target[index]) index++;
      if (index >= target.length) return;
      segmentAssisted = true;
      // Replace the first mismatch, including incomplete words, without shifting contractions.
      user[index] = target[index];
      input.value = user.slice(0, Math.max(index + 1, user.length)).join(' ') + ' ';
      onDictationInput(input.value); focusDictationInput();
    }
    function giveUpAndReveal() {
      const seg = currentSegment();
      if (!seg || segmentUnlocked) return;
      segmentAssisted = true;
      renderWordSlots(getCleanTargetTokens(seg.en));
      handleSegmentSuccess(seg, 'revealed');
      // Revealing never silently adds a card to the user's collection.
    }
    function updatePendingListening() {
      const count = Object.keys(pendingListening).length;
      document.getElementById('listening-pending-count').textContent = count ? '(' + count + ')' : '(0)';
    }
    async function sendListeningPayload(payload) {
      const key = payload.id;
      if (sentListening[key]) { showToast('Este trecho já está na fila do Anki Hub.'); return true; }
      if (listeningSends.has(key)) return listeningSends.get(key);
      const request = (async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);
        try {
          const response = await fetch('/api/evaluate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal });
          if (!response.ok) throw Error('HTTP ' + response.status);
          const result = await response.json();
          if (!result.success) throw Error(result.error || 'O servidor não confirmou o salvamento.');
          sentListening[key] = true; delete pendingListening[key];
          writeListeningStore(LISTENING_STORAGE + '_sent', sentListening);
          writeListeningStore(LISTENING_STORAGE + '_pending', pendingListening);
          updatePendingListening();
          showToast('Trecho adicionado à fila do Anki Hub. A criação do cartão ocorre no envio da fila.');
          fetchStatus();
          return true;
        } catch (error) {
          pendingListening[key] = payload;
          const saved = writeListeningStore(LISTENING_STORAGE + '_pending', pendingListening);
          updatePendingListening();
          showToast(saved ? 'Envio não confirmado. Trecho salvo neste navegador para reenvio.' : 'Envio não confirmado. Pendência mantida apenas nesta aba.', false);
          return false;
        } finally { clearTimeout(timeout); listeningSends.delete(key); }
      })();
      listeningSends.set(key, request);
      return request;
    }
    function saveListeningSegment(seg, source) {
      if (!seg || !seg.en) return Promise.resolve(false);
      return sendListeningPayload({ id: 'listening_' + listeningHash(JSON.stringify([source, seg.start, seg.end, seg.en])),
        word: seg.en, pos: 'LISTENING', subdeck: 'listening-studio', definition_en: 'Frase de Listening: ' + seg.en,
        definition_pt: seg.pt || '', example_1: seg.en, card_id: null, status: 'desconhecido' });
    }
    function saveCurrentSegmentToAnki() { return saveListeningSegment(currentSegment(), activeVideoData.videoId || activeVideoData.identity || activeVideoData.title); }
    async function retryPendingListening() {
      const pending = Object.values(pendingListening);
      if (!pending.length) return showToast('Nenhum envio pendente.');
      for (const payload of pending) await sendListeningPayload(payload);
    }
    function onSelectVideoPreset(key) {
      if (!VIDEO_PRESETS[key]) return showToast('Este treino aguarda validação da fonte e das legendas.', false);
      pauseListeningMedia(); selectedYoutubeData = structuredClone(VIDEO_PRESETS[key]);
      if (VideoController.isLocal) switchVideoSource('youtube');
      else { activeVideoData = selectedYoutubeData; activateDictationData(); }
      if (ytReady) ytPlayer.cueVideoById(activeVideoData.videoId);
      else initYouTubePlayer();
      if (activeVideoData && activeVideoData.videoId) {
        fetchYoutubeTranscript(activeVideoData.videoId);
      }
    }
    function loadVideoFromInput() {
      let url;
      try { url = new URL(document.getElementById('yt-url-input').value.trim()); }
      catch (_) { return showToast('Cole uma URL válida do YouTube.', false); }
      const host = url.hostname.toLowerCase();
      let id = null;
      if (['youtu.be', 'www.youtu.be'].includes(host)) id = url.pathname.split('/')[1];
      if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'www.youtube-nocookie.com'].includes(host)) {
        id = url.searchParams.get('v') || (/^\/(embed|shorts|live)\//.test(url.pathname) ? url.pathname.split('/')[2] : null);
      }
      if (!['http:', 'https:'].includes(url.protocol) || !/^[\w-]{11}$/.test(id || '')) return showToast('Link do YouTube inválido.', false);
      pauseListeningMedia();
      selectedYoutubeData = { videoId: id, title: 'Vídeo personalizado', segments: [] };
      if (VideoController.isLocal) switchVideoSource('youtube');
      else { activeVideoData = selectedYoutubeData; activateDictationData(); }
      if (ytReady) ytPlayer.cueVideoById(id); else initYouTubePlayer();
      showToast('Vídeo selecionado. Carregando legendas do YouTube...');
      fetchYoutubeTranscript(id);
    }

    // Real audio-only practice with optional time-aligned transcript.
    function listeningAudio() { return document.getElementById('listening-audio'); }
    function initListeningWaveform() {
      const container = document.getElementById('listening-waveform');
      if (container.children.length) return;
      for (let i = 0; i < 48; i++) { const bar = document.createElement('i'); bar.style.height = (10 + Math.abs(Math.sin(i * 1.9) * Math.cos(i * .32)) * 52) + 'px'; container.appendChild(bar); }
    }
    function onListeningAudioSelected(event) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      stopListeningAudio();
      if (audioObjectURL) URL.revokeObjectURL(audioObjectURL);
      audioObjectURL = URL.createObjectURL(file);
      audioTracks = []; audioTrackIndex = 0;
      const audio = listeningAudio(); audio.src = audioObjectURL; audio.load();
      document.getElementById('listening-file-status').textContent = file.name + ' · Importe a transcrição se quiser comparar por trecho.';
      hideListeningTranscript(); updateListeningTime();
    }
    function toggleListeningPlay() { listeningAudio().paused ? startListeningAudio() : stopListeningAudio(); }
    function startListeningAudio() {
      const audio = listeningAudio();
      if (!audio.src) return showToast('Escolha primeiro um arquivo de áudio ou vídeo.', false);
      const track = audioTracks[audioTrackIndex];
      if (audio.ended || (track && (audio.currentTime >= track.end || audio.currentTime < track.start))) audio.currentTime = track ? track.start : 0;
      audio.playbackRate = listeningRate;
      audio.play().catch(() => showToast('Não foi possível reproduzir este áudio. Verifique o formato.', false));
    }
    function stopListeningAudio() {
      const audio = listeningAudio();
      if (audio) audio.pause();
      const btn = document.getElementById('listening-play-btn');
      if (btn) { btn.textContent = '▶'; btn.setAttribute('aria-label', 'Reproduzir áudio'); }
    }
    function onListeningSeek(value) {
      const audio = listeningAudio(), seconds = Number(value);
      if (!Number.isFinite(audio.duration) || !Number.isFinite(seconds)) return;
      const track = audioTracks[audioTrackIndex];
      audio.currentTime = track ? Math.max(track.start, Math.min(track.end, seconds)) : Math.max(0, Math.min(audio.duration, seconds));
      updateListeningTime();
    }
    function seekListeningDelta(delta) { onListeningSeek(listeningAudio().currentTime + delta); }
    function updateListeningTime() {
      const audio = listeningAudio();
      const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
      const seek = document.getElementById('listening-seek');
      seek.max = duration; seek.value = audio.currentTime || 0;
      const clock = seconds => { const n = Math.floor(seconds || 0); return String(Math.floor(n / 60)).padStart(2, '0') + ':' + String(n % 60).padStart(2, '0'); };
      document.getElementById('listening-elapsed').textContent = clock(audio.currentTime);
      document.getElementById('listening-total').textContent = clock(duration);
      const bars = document.querySelectorAll('#listening-waveform i');
      bars.forEach((bar, i) => bar.classList.toggle('played', duration > 0 && i < bars.length * audio.currentTime / duration));
      document.getElementById('listening-track-label').textContent = audioTracks.length ? 'TRECHO ' + (audioTrackIndex + 1) + ' / ' + audioTracks.length : 'ARQUIVO LOCAL';
      document.getElementById('listening-session-metric').textContent = audioTracks.length ? (audioTrackIndex + 1) + ' / ' + audioTracks.length + ' trechos' : 'Sem legenda';
      document.getElementById('listening-session-progress').style.width = audioTracks.length ? ((audioTrackIndex + 1) / audioTracks.length * 100) + '%' : '0%';
      const track = audioTracks[audioTrackIndex];
      if (track && audio.currentTime >= track.end && !audio.paused) stopListeningAudio();
    }
    function cycleListeningSpeed() {
      listeningRate = listeningRate === 1 ? 1.25 : listeningRate === 1.25 ? 1.5 : listeningRate === 1.5 ? .75 : 1;
      listeningAudio().playbackRate = listeningRate;
      document.getElementById('listening-speed-btn').textContent = listeningRate + '×';
    }
    function hideListeningTranscript() {
      document.getElementById('listening-transcript-box').style.display = 'none';
      document.getElementById('btn-reveal-transcript').textContent = 'Revelar transcrição';
      document.getElementById('btn-reveal-transcript').setAttribute('aria-expanded', 'false');
      document.getElementById('btn-save-listening-anki').disabled = !audioTracks[audioTrackIndex];
    }
    function toggleListeningReveal() {
      const track = audioTracks[audioTrackIndex];
      if (!track) return showToast('Importe uma transcrição SRT/VTT para este áudio.', false);
      const box = document.getElementById('listening-transcript-box');
      const reveal = box.style.display === 'none';
      box.style.display = reveal ? 'block' : 'none';
      document.getElementById('listening-sentence-en').textContent = track.en;
      document.getElementById('listening-sentence-pt').textContent = track.pt || '';
      const btn = document.getElementById('btn-reveal-transcript');
      btn.textContent = reveal ? 'Ocultar transcrição' : 'Revelar transcrição'; btn.setAttribute('aria-expanded', String(reveal));
    }
    function saveListeningToAnki() { return saveListeningSegment(audioTracks[audioTrackIndex], document.getElementById('listening-file-status').textContent); }
    function selectListeningTrack(index) {
      const track = audioTracks[index];
      if (!track) return;
      stopListeningAudio(); audioTrackIndex = index;
      const audio = listeningAudio();
      if (audio.readyState >= 1) audio.currentTime = track.start;
      hideListeningTranscript(); updateListeningTime();
    }
    function stepListeningTrack(delta) { selectListeningTrack(audioTrackIndex + delta); }
    function restartListeningSession() {
      stopListeningAudio();
      if (audioTracks.length) selectListeningTrack(0); else if (listeningAudio().readyState >= 1) listeningAudio().currentTime = 0;
      hideListeningTranscript(); updateListeningTime();
    }
    window.addEventListener('DOMContentLoaded', () => {
      initListeningWaveform(); updatePendingListening(); activateDictationData();
      const audio = listeningAudio();
      audio.addEventListener('timeupdate', updateListeningTime);
      audio.addEventListener('loadedmetadata', updateListeningTime);
      audio.addEventListener('ended', stopListeningAudio);
      audio.addEventListener('pause', stopListeningAudio);
      audio.addEventListener('play', () => {
        const btn = document.getElementById('listening-play-btn'); btn.textContent = 'Ⅱ'; btn.setAttribute('aria-label', 'Pausar áudio');
      });
      audio.addEventListener('error', () => { stopListeningAudio(); showToast('O navegador não conseguiu abrir este áudio.', false); });
      updateListeningTime();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && !(selectedListeningSubmode === 'podcast' && podcastPlaying)) {
        pauseListeningMedia();
      }
    });
    window.addEventListener('pagehide', pauseListeningMedia);

    // ==========================================
    // SUBMODO 3: PODCAST CONTINUO DE IMERSAO + MEDIASESSION API
    // ==========================================
    let podcastTracks = [];
    let podcastIndex = 0;
    let podcastPlaying = false;
    let podcastPass = 1;
    let podcastRate = 1.0;
    let podcastBlind = false;
    let podcastTimer = null;
    let podcastActiveUtterance = null;

    function escapeHtmlSafe(str) {
      return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    async function loadImmersionPlaylist(notifyUser = false) {
      stopPodcastPlayback();
      const srcEl = document.getElementById('podcast-source-select');
      const source = srcEl ? srcEl.value : 'gaps';
      const deckSel = document.getElementById('select-subdeck');
      const subdeck = deckSel ? deckSel.value : '01k';
      try {
        const resp = await fetch(`/api/immersion-playlist?source=${encodeURIComponent(source)}&subdeck=${encodeURIComponent(subdeck)}&limit=45`);
        const data = await resp.json();
        podcastTracks = (data && Array.isArray(data.tracks)) ? data.tracks : [];
        podcastIndex = 0;
        podcastPass = 1;
        renderPodcastState();
        renderPodcastQueue();
        if (notifyUser) showToast(`${podcastTracks.length} faixas carregadas na playlist de imersao.`);
      } catch (err) {
        showToast('Falha ao carregar playlist de imersao.', false);
      }
    }

    function renderPodcastQueue() {
      const box = document.getElementById('podcast-queue-list');
      if (!box) return;
      if (!podcastTracks.length) {
        box.innerHTML = '<div style="color: var(--muted); font-size: 12px;">Nenhuma faixa encontrada para este filtro.</div>';
        return;
      }
      box.innerHTML = podcastTracks.map((tr, i) => {
        const active = i === podcastIndex;
        return `<button type="button" onclick="selectPodcastTrack(${i})" style="text-align: left; padding: 8px 10px; border-radius: 8px; border: 1px solid ${active ? 'var(--cyan)' : 'var(--line)'}; background: ${active ? 'rgba(101, 225, 216, 0.10)' : 'rgba(255,255,255,0.02)'}; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: ${active ? '700' : '500'}; color: ${active ? 'var(--cyan)' : 'var(--text)'};">${String(i + 1).padStart(2, '0')}. ${escapeHtmlSafe(tr.word)}</span>
          <span style="font-size: 10px; color: var(--muted); text-transform: uppercase;">${escapeHtmlSafe(tr.subdeck)}</span>
        </button>`;
      }).join('');
    }

    function renderPodcastState() {
      const total = podcastTracks.length;
      const tr = podcastTracks[podcastIndex];
      const counter = document.getElementById('podcast-track-counter');
      const wordBadge = document.getElementById('podcast-word-badge');
      const srcTag = document.getElementById('podcast-audio-source-tag');
      const enEl = document.getElementById('podcast-sentence-en');
      const ptEl = document.getElementById('podcast-sentence-pt');
      const metricEl = document.getElementById('podcast-session-metric');
      const progEl = document.getElementById('podcast-session-progress');
      const passEl = document.getElementById('podcast-pass-indicator');

      if (!tr) {
        if (counter) counter.textContent = 'FAIXA 00 / 00';
        if (enEl) enEl.textContent = 'Nenhuma frase disponivel no filtro atual.';
        if (ptEl) ptEl.textContent = 'Selecione outro filtro de origem acima.';
        if (metricEl) metricEl.innerHTML = '0 <small>/ 0 faixas</small>';
        if (progEl) progEl.style.width = '0%';
        return;
      }

      const maxPasses = Number(document.getElementById('podcast-repeat-select')?.value || 2);
      if (counter) counter.textContent = `FAIXA ${String(podcastIndex + 1).padStart(2, '0')} / ${String(total).padStart(2, '0')}`;
      if (passEl) passEl.textContent = podcastPlaying ? `Escuta ${podcastPass} de ${maxPasses}` : 'Pausado';
      if (wordBadge) wordBadge.textContent = `${tr.word}${tr.ipa ? ' /' + tr.ipa + '/' : ''} · ${(tr.subdeck || '').toUpperCase()}`;
      if (srcTag) {
        srcTag.textContent = tr.audio_type === 'sentence_native' ? 'Frase Nativa' : (tr.audio_type === 'word_native' ? 'Voz Dicionario + TTS' : 'Sintese Nativa');
      }
      if (enEl) enEl.textContent = podcastBlind ? '● ● ●   Modo Cego Ativo — Foque 100% na compreensao auditiva   ● ● ●' : tr.en;
      if (ptEl) ptEl.textContent = podcastBlind ? 'Clique em Mostrar Texto caso precise conferir a transcricao.' : (tr.pt || tr.def_en || '');
      if (metricEl) metricEl.innerHTML = `${podcastIndex + 1} <small>/ ${total} faixas</small>`;
      if (progEl) progEl.style.width = `${Math.round(((podcastIndex + 1) / total) * 100)}%`;
      updatePodcastMediaSession(tr);
    }

    function updatePodcastMediaSession(tr) {
      if (!('mediaSession' in navigator) || !tr) return;
      try {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: podcastBlind ? `Faixa ${podcastIndex + 1} (${tr.subdeck.toUpperCase()})` : `${tr.word} — ${tr.en}`,
          artist: 'Lexis Immersion Studio',
          album: `Deck ${(tr.subdeck || 'Lexis').toUpperCase()} · Comprehensible Input`
        });
        navigator.mediaSession.playbackState = podcastPlaying ? 'playing' : 'paused';
        navigator.mediaSession.setActionHandler('play', () => { if (!podcastPlaying) startPodcastPlayback(); });
        navigator.mediaSession.setActionHandler('pause', () => { if (podcastPlaying) stopPodcastPlayback(); });
        navigator.mediaSession.setActionHandler('previoustrack', () => stepPodcastTrack(-1));
        navigator.mediaSession.setActionHandler('nexttrack', () => stepPodcastTrack(1));
      } catch (_) {}
    }

    function togglePodcastPlayback() {
      if (podcastPlaying) stopPodcastPlayback();
      else startPodcastPlayback();
    }

    function startPodcastPlayback() {
      if (!podcastTracks.length) {
        loadImmersionPlaylist().then(() => { if (podcastTracks.length) startPodcastPlayback(); });
        return;
      }
      podcastPlaying = true;
      const btn = document.getElementById('podcast-play-btn');
      if (btn) { btn.textContent = 'Ⅱ'; btn.setAttribute('aria-label', 'Pausar imersao'); }
      renderPodcastState();
      playCurrentPodcastPass();
    }

    function stopPodcastPlayback() {
      podcastPlaying = false;
      if (podcastTimer) { clearTimeout(podcastTimer); podcastTimer = null; }
      const audioEl = document.getElementById('podcast-audio-el');
      if (audioEl) { audioEl.onended = null; audioEl.onerror = null; audioEl.pause(); }
      if ('speechSynthesis' in window) { try { window.speechSynthesis.cancel(); } catch (_) {} }
      const btn = document.getElementById('podcast-play-btn');
      if (btn) { btn.textContent = '▶'; btn.setAttribute('aria-label', 'Iniciar imersao'); }
      const passEl = document.getElementById('podcast-pass-indicator');
      if (passEl) passEl.textContent = 'Pausado';
      if ('mediaSession' in navigator) { try { navigator.mediaSession.playbackState = 'paused'; } catch (_) {} }
    }

    function scheduleNextPodcastStep() {
      if (!podcastPlaying) return;
      const maxPasses = Number(document.getElementById('podcast-repeat-select')?.value || 2);
      const gapMs = Number(document.getElementById('podcast-gap-select')?.value || 2500);
      const passEl = document.getElementById('podcast-pass-indicator');
      if (podcastPass < maxPasses) {
        podcastPass += 1;
        if (passEl) passEl.textContent = `Pausa reflexiva (${(gapMs / 1000).toFixed(1)}s) -> Repeticao ${podcastPass}/${maxPasses}`;
        podcastTimer = setTimeout(() => { if (podcastPlaying) playCurrentPodcastPass(); }, gapMs);
      } else {
        podcastPass = 1;
        podcastIndex = (podcastIndex + 1) % podcastTracks.length;
        if (passEl) passEl.textContent = `Intervalo (${(gapMs / 1000).toFixed(1)}s) -> Proxima faixa`;
        podcastTimer = setTimeout(() => {
          if (!podcastPlaying) return;
          renderPodcastState();
          renderPodcastQueue();
          playCurrentPodcastPass();
        }, gapMs);
      }
    }

    function speakSentenceFallback(text, onDone) {
      if (!('speechSynthesis' in window)) { onDone(); return; }
      try {
        window.speechSynthesis.cancel();
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = 'en-US';
        utt.rate = podcastRate;
        podcastActiveUtterance = utt;
        utt.onend = () => { podcastActiveUtterance = null; onDone(); };
        utt.onerror = () => { podcastActiveUtterance = null; onDone(); };
        window.speechSynthesis.speak(utt);
      } catch (_) {
        onDone();
      }
    }

    function playCurrentPodcastPass() {
      if (!podcastPlaying) return;
      const tr = podcastTracks[podcastIndex];
      if (!tr) { stopPodcastPlayback(); return; }
      renderPodcastState();
      const audioEl = document.getElementById('podcast-audio-el');

      if (tr.audio_url && tr.audio_type === 'sentence_native' && audioEl) {
        audioEl.src = tr.audio_url;
        audioEl.playbackRate = podcastRate;
        audioEl.onended = () => scheduleNextPodcastStep();
        audioEl.onerror = () => speakSentenceFallback(tr.en, scheduleNextPodcastStep);
        audioEl.play().catch(() => speakSentenceFallback(tr.en, scheduleNextPodcastStep));
      } else if (tr.audio_url && tr.audio_type === 'word_native' && audioEl && podcastPass === 1) {
        audioEl.src = tr.audio_url;
        audioEl.playbackRate = podcastRate;
        audioEl.onended = () => {
          if (!podcastPlaying) return;
          setTimeout(() => { if (podcastPlaying) speakSentenceFallback(tr.en, scheduleNextPodcastStep); }, 350);
        };
        audioEl.onerror = () => speakSentenceFallback(tr.en, scheduleNextPodcastStep);
        audioEl.play().catch(() => speakSentenceFallback(tr.en, scheduleNextPodcastStep));
      } else {
        speakSentenceFallback(tr.en, scheduleNextPodcastStep);
      }
    }

    function selectPodcastTrack(idx) {
      if (idx < 0 || idx >= podcastTracks.length) return;
      const wasPlaying = podcastPlaying;
      stopPodcastPlayback();
      podcastIndex = idx;
      podcastPass = 1;
      renderPodcastState();
      renderPodcastQueue();
      if (wasPlaying) startPodcastPlayback();
    }

    function stepPodcastTrack(delta) {
      if (!podcastTracks.length) return;
      const next = (podcastIndex + delta + podcastTracks.length) % podcastTracks.length;
      selectPodcastTrack(next);
    }

    function cyclePodcastSpeed() {
      const speeds = [1.0, 0.85, 1.15];
      podcastRate = speeds[(speeds.indexOf(podcastRate) + 1) % speeds.length];
      const btn = document.getElementById('podcast-speed-btn');
      if (btn) btn.textContent = podcastRate.toFixed(2).replace(/\.00$/, '.0') + 'x';
      const audioEl = document.getElementById('podcast-audio-el');
      if (audioEl) audioEl.playbackRate = podcastRate;
    }

    function togglePodcastBlindMode() {
      podcastBlind = !podcastBlind;
      const btn = document.getElementById('podcast-blind-btn');
      if (btn) btn.textContent = podcastBlind ? 'Mostrar Texto (Transcricao)' : 'Ocultar Texto (Modo Cego)';
      renderPodcastState();
    }

    function onPodcastConfigChange() {
      podcastPass = 1;
      renderPodcastState();
    }

    async function flagCurrentPodcastTrackAsGap() {
      const tr = podcastTracks[podcastIndex];
      if (!tr) return;
      try {
        const res = await fetch('/api/evaluate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: `${tr.word.toLowerCase()}_immersion`,
            word: tr.word,
            status: 'desconhecido',
            pos: tr.pos || 'IMMERSION',
            subdeck: tr.subdeck || '01k',
            definition_en: tr.def_en || tr.en,
            definition_pt: tr.pt || '',
            example_1: tr.en
          })
        });
        const data = await res.json();
        if (data && data.success) {
          showToast(`"${tr.word}" enviado para a Fila prioritaria do Anki.`);
          fetchStatus();
        }
      } catch (_) {
        showToast('Nao foi possivel registrar o termo agora.', false);
      }
    }

    // ==========================================
    // MODULO 3: ANKI HUB COMMAND CENTER
    // ==========================================
    function playHubAudioUrl(url) {
      if (!url) return;
      try {
        if (currentAudioObj) currentAudioObj.pause();
        currentAudioObj = new Audio(url);
        currentAudioObj.play().catch(() => showToast('Audio indisponivel localmente.', false));
      } catch (_) {}
    }

    async function loadAnkiHubModule(notifyUser = false) {
      try {
        const res = await fetch('/api/anki-hub');
        const data = await res.json();
        if (!data || !data.success) return;

        const stEl = document.getElementById('hub-kpi-anki-status');
        const subEl = document.getElementById('hub-kpi-anki-sub');
        if (stEl) {
          stEl.textContent = data.anki_connected ? `Online (v${data.anki_version || 6})` : 'Anki Desktop Fechado';
          stEl.style.color = data.anki_connected ? '#34d399' : 'var(--amber)';
        }
        if (subEl) {
          subEl.textContent = data.anki_connected
            ? `${data.deck_card_count !== null ? data.deck_card_count + ' cartoes ativos no baralho' : 'AnkiConnect pronto em 127.0.0.1:8765'}`
            : 'Abra o Anki com AnkiConnect para injetar os Gaps prontos';
        }

        document.getElementById('hub-kpi-ready').textContent = data.pipeline.ready_count;
        document.getElementById('hub-kpi-waiting').textContent = data.pipeline.waiting_count;
        document.getElementById('hub-kpi-injected').textContent = data.pipeline.injected_count;

        const tbody = document.getElementById('hub-ready-tbody');
        if (tbody) {
          if (!data.top_ready.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="padding: 18px 6px; color: var(--muted); text-align: center;">Nenhum Gap pendente com frase pronta no momento.</td></tr>';
          } else {
            tbody.innerHTML = data.top_ready.map(item => {
              const safeAudio = item.audio_url ? item.audio_url.replace(/'/g, "\\'") : '';
              return `<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                <td style="padding: 9px 6px;"><span style="font-size: 11px; padding: 2px 7px; border-radius: 6px; background: rgba(101, 225, 216, 0.12); color: var(--cyan); font-weight: 700;">${escapeHtmlSafe((item.subdeck || '').toUpperCase())}</span></td>
                <td style="padding: 9px 6px; font-weight: 700; color: var(--text);">${escapeHtmlSafe(item.termo_display)} <small style="color: var(--muted); font-weight: 400;">${escapeHtmlSafe(item.pos)}</small></td>
                <td style="padding: 9px 6px; color: #cbd5e1; font-size: 12px;">${escapeHtmlSafe(item.frase)}<div style="color: var(--muted); font-size: 11px; margin-top: 2px;">${escapeHtmlSafe(item.definicao_pt || item.definicao)}</div></td>
                <td style="padding: 9px 6px; text-align: right;">${safeAudio ? `<button type="button" class="dictation-btn" style="padding: 3px 8px; font-size: 11px;" onclick="playHubAudioUrl('${safeAudio}')">▶</button>` : '<span style="color: var(--muted); font-size: 11px;">--</span>'}</td>
              </tr>`;
            }).join('');
          }
        }

        const injBox = document.getElementById('hub-injected-list');
        if (injBox) {
          if (!data.recent_injected.length) {
            injBox.innerHTML = '<div style="color: var(--muted); font-size: 12px; padding: 12px 0;">Nenhuma injecao registrada ainda no mapa local.</div>';
          } else {
            injBox.innerHTML = data.recent_injected.slice(0, 14).map(it => {
              const dt = (it.injetado_em || it.confirmado_em || '').slice(0, 10) || 'Vinculado';
              return `<div style="padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: rgba(255,255,255,0.02);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <strong style="color: var(--text); font-size: 13px;">${escapeHtmlSafe(it.termo_display)}</strong>
                  <span style="font-size: 10px; color: var(--blue); border: 1px solid rgba(128,184,255,0.3); padding: 1px 6px; border-radius: 4px;">${escapeHtmlSafe(dt)}</span>
                </div>
                <div style="font-size: 11px; color: var(--muted); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtmlSafe(it.frase || it.definicao)}</div>
              </div>`;
            }).join('');
          }
        }

        if (notifyUser) showToast('Status do Anki Hub atualizado.');
      } catch (_) {
        showToast('Erro ao consultar /api/anki-hub.', false);
      }
    }

    async function hubEnrichGaps() {
      const btn = document.getElementById('hub-btn-enrich');
      if (btn) btn.disabled = true;
      await enrichAllGaps();
      await loadAnkiHubModule();
      if (btn) btn.disabled = false;
    }

    async function hubSyncCloud() {
      const btn = document.getElementById('hub-btn-sync');
      if (btn) btn.disabled = true;
      await syncWithCloud();
      await loadAnkiHubModule();
      if (btn) btn.disabled = false;
    }

    async function hubInjectAnki() {
      const btn = document.getElementById('hub-btn-inject');
      const qty = document.getElementById('hub-inject-limit')?.value || '10';
      if (btn) btn.disabled = true;
      showToast('Executando injecao cirurgica no Anki via AnkiConnect...');
      try {
        const res = await fetch('/api/inject-anki', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ limit: qty })
        });
        const data = await res.json();
        if (data && data.success) {
          showToast(data.message || 'Cartoes injetados com sucesso.');
          await fetchStatus();
          await loadAnkiHubModule();
        } else {
          showToast((data && (data.message || data.error)) || 'Abra o Anki Desktop para concluir a injecao.', false);
        }
      } catch (_) {
        showToast('Erro de comunicacao com o servidor local.', false);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    // ==========================================
    // MODULO 4: ANALYTICS & COBERTURA CEFR
    // ==========================================
    function jumpToDeckFromAnalytics(subdeck) {
      const sel = document.getElementById('select-subdeck');
      if (sel) {
        sel.value = subdeck;
        onSubdeckChange();
      }
      switchModule('vocab');
    }

    function launchHighLeverageSprint(subdeck) {
      const sel = document.getElementById('select-subdeck');
      if (sel) {
        sel.value = subdeck;
        onSubdeckChange();
      }
      switchView('focus');
      showToast(`Sprint iniciado em ${subdeck.toUpperCase()} · Modo Foco ativo.`);
    }

    function launchImmersionOnGaps() {
      switchModule('listening');
      switchListeningSubmode('podcast');
      const srcEl = document.getElementById('podcast-source-select');
      if (srcEl) srcEl.value = 'gaps';
      loadImmersionPlaylist(true);
    }

    let lastAnalyticsData = null;
    let currentAnalyticsView = "bars";
    let analyticsTimelineStyle = "bars";

    function switchAnalyticsView(mode) {
      currentAnalyticsView = mode || "bars";
      document.querySelectorAll("#ana-view-tabs .mode-pill-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.anaView === currentAnalyticsView);
      });
      if (lastAnalyticsData) renderAnalyticsMainView(lastAnalyticsData);
    }

    function toggleAnalyticsTimelineStyle() {
      analyticsTimelineStyle = analyticsTimelineStyle === "bars" ? "line" : "bars";
      const btn = document.getElementById("ana-tl-toggle");
      if (btn) btn.textContent = analyticsTimelineStyle === "bars" ? "Ver Linha" : "Ver Barras";
      if (lastAnalyticsData) renderAnalyticsTimeline(lastAnalyticsData.daily_timeline || []);
    }

    function renderAnalyticsBandRow(b) {
      const t = Math.max(1, b.total || 1);
      const pKnown = Math.min(100, (b.known / t) * 100);
      const pGaps = Math.min(100 - pKnown, (b.gaps / t) * 100);
      const pDoubts = Math.min(100 - pKnown - pGaps, (b.doubts / t) * 100);
      return `<div class="ana-band-row" onclick="jumpToDeckFromAnalytics('${escapeHtmlSafe(b.subdeck)}')">
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 6px; gap: 8px;">
          <div>
            <strong style="color: var(--text);">${escapeHtmlSafe(b.subdeck.toUpperCase())}</strong>
            <span style="color: var(--cyan); font-size: 11px; margin-left: 6px; font-weight: 600;">${escapeHtmlSafe(b.cefr_code)}</span>
            <span style="color: var(--muted); font-size: 11px; margin-left: 6px;">${escapeHtmlSafe(b.label)}</span>
          </div>
          <span class="tnum" style="font-family: var(--font-mono); font-size: 11px; color: var(--muted); white-space: nowrap;">${b.evaluated}/${b.total} (${b.percent}%)</span>
        </div>
        <div class="ana-track">
          <span style="width: ${pKnown.toFixed(1)}%; background: var(--color-known);"></span>
          <span style="width: ${pGaps.toFixed(1)}%; background: var(--color-unknown);"></span>
          <span style="width: ${pDoubts.toFixed(1)}%; background: var(--color-doubt);"></span>
        </div>
      </div>`;
    }

    function renderAnalyticsRadarSvg(bands) {
      if (!bands.length) return "";
      const cx = 210, cy = 180, rMax = 128;
      const n = bands.length;
      const angleFor = (i) => (-Math.PI / 2) + (2 * Math.PI * i) / n;
      const pt = (i, pct) => {
        const rad = (Math.max(4, Math.min(100, pct)) / 100) * rMax;
        const a = angleFor(i);
        return [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
      };

      const rings = [25, 50, 75, 100].map((lvl) => {
        const pts = bands.map((_, i) => pt(i, lvl).map(v => v.toFixed(1)).join(",")).join(" ");
        return `<polygon points="${pts}" fill="none" stroke="var(--line)" stroke-width="1"/>`;
      }).join("");

      const spokes = bands.map((b, i) => {
        const [x2, y2] = pt(i, 100);
        const [lx, ly] = [cx + Math.cos(angleFor(i)) * (rMax + 22), cy + Math.sin(angleFor(i)) * (rMax + 20)];
        return `<line x1="${cx}" y1="${cy}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>
          <text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" dominant-baseline="middle" fill="var(--muted)" font-size="11" font-weight="600" style="cursor:pointer;" onclick="jumpToDeckFromAnalytics('${escapeHtmlSafe(b.subdeck)}')">${escapeHtmlSafe(b.subdeck.toUpperCase())}</text>`;
      }).join("");

      const evalPoly = bands.map((b, i) => pt(i, b.percent || 0).map(v => v.toFixed(1)).join(",")).join(" ");
      const knownPoly = bands.map((b, i) => {
        const kPct = b.total ? (b.known / b.total) * 100 : 0;
        return pt(i, kPct).map(v => v.toFixed(1)).join(",");
      }).join(" ");

      const nodes = bands.map((b, i) => {
        const [x, y] = pt(i, b.percent || 0);
        return `<circle class="ana-radar-node" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="var(--cyan)" stroke="var(--card)" stroke-width="1.5" onclick="jumpToDeckFromAnalytics('${escapeHtmlSafe(b.subdeck)}')">
          <title>${escapeHtmlSafe(b.subdeck.toUpperCase())} (${escapeHtmlSafe(b.cefr_code)}): ${b.percent}% avaliado · ${b.known} conhecidos · ${b.gaps} gaps</title>
        </circle>`;
      }).join("");

      return `<div class="ana-svg-stage">
        <svg viewBox="0 0 420 365" style="max-width: 440px;" role="img" aria-label="Gráfico Radar CEFR de cobertura léxica">
          ${rings}
          ${spokes}
          <polygon points="${evalPoly}" fill="color-mix(in oklab, var(--cyan) 20%, transparent)" stroke="var(--cyan)" stroke-width="2"/>
          <polygon points="${knownPoly}" fill="color-mix(in oklab, var(--color-known) 24%, transparent)" stroke="var(--color-known)" stroke-width="2"/>
          ${nodes}
        </svg>
        <div class="ana-legend-row">
          <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--cyan);"></span>Cobertura Avaliada (%)</span>
          <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--color-known);"></span>Domínio Direto (Conhecidos %)</span>
          <span class="ana-legend-item" style="color: var(--dim);">Clique em qualquer eixo para abrir o deck</span>
        </div>
      </div>`;
    }

    function renderAnalyticsHeatmap(bands) {
      const cells = bands.map((b) => {
        const pct = Number(b.percent || 0);
        const mastery = b.evaluated > 0 ? Math.round((b.known / b.evaluated) * 100) : 0;
        const mixPct = Math.min(34, Math.max(4, Math.round(pct * 0.34)));
        const tintColor = pct >= 50 ? "var(--color-known)" : (pct > 0 ? "var(--cyan)" : "var(--text)");
        const bgStyle = pct > 0
          ? `background: color-mix(in oklab, ${tintColor} ${mixPct}%, var(--surface));`
          : `background: var(--surface);`;
        return `<div class="ana-heatmap-cell" style="${bgStyle}" onclick="jumpToDeckFromAnalytics('${escapeHtmlSafe(b.subdeck)}')">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong style="font-size: 13px;">${escapeHtmlSafe(b.subdeck.toUpperCase())} <span style="color: var(--cyan); font-weight: 600; font-size: 11px; margin-left: 4px;">${escapeHtmlSafe(b.cefr_code)}</span></strong>
            <span style="font-size: 11px; color: var(--muted); font-family: var(--font-mono);">${b.evaluated}/${b.total}</span>
          </div>
          <div style="display: flex; align-items: baseline; justify-content: space-between;">
            <span class="ana-heatmap-pct" style="color: ${pct >= 50 ? 'var(--color-known)' : 'var(--text)'};">${pct}%</span>
            <span style="font-size: 11px; color: var(--muted);">Acerto: <strong style="color: var(--text);">${mastery}%</strong> · Gaps: <strong style="color: var(--color-unknown);">${b.gaps}</strong></span>
          </div>
          <div style="font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtmlSafe(b.label)}</div>
        </div>`;
      }).join("");
      return `<div class="ana-heatmap-grid">${cells}</div>`;
    }

    function renderAnalyticsCurveSvg(bands) {
      if (!bands.length) return "";
      const w = 540, h = 270, padL = 38, padR = 16, padT = 20, padB = 34;
      const plotW = w - padL - padR;
      const plotH = h - padT - padB;
      const xFor = (i) => padL + (bands.length === 1 ? plotW / 2 : (i / (bands.length - 1)) * plotW);
      const yFor = (pct) => padT + plotH - (Math.min(100, Math.max(0, pct)) / 100) * plotH;

      const gridLines = [0, 25, 50, 75, 100].map((v) => {
        const y = yFor(v).toFixed(1);
        return `<line x1="${padL}" y1="${y}" x2="${w - padR}" y2="${y}" stroke="var(--line)" stroke-width="1"/>
          <text x="${padL - 8}" y="${y}" text-anchor="end" dominant-baseline="middle" fill="var(--dim)" font-size="10">${v}%</text>`;
      }).join("");

      const evalPts = bands.map((b, i) => [xFor(i), yFor(b.percent || 0)]);
      const knownPts = bands.map((b, i) => [xFor(i), yFor(b.total ? (b.known / b.total) * 100 : 0)]);
      const lineStr = (pts) => pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
      const areaStr = (pts) => `${padL},${(padT + plotH).toFixed(1)} ${lineStr(pts)} ${xFor(bands.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)}`;

      const labels = bands.map((b, i) => {
        const x = xFor(i).toFixed(1);
        return `<text x="${x}" y="${h - 10}" text-anchor="middle" fill="var(--muted)" font-size="10" font-weight="600" style="cursor:pointer;" onclick="jumpToDeckFromAnalytics('${escapeHtmlSafe(b.subdeck)}')">${escapeHtmlSafe(b.subdeck.toUpperCase())}</text>`;
      }).join("");

      const dots = bands.map((b, i) => {
        const [x, y] = evalPts[i];
        return `<circle class="ana-radar-node" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="var(--cyan)" stroke="var(--card)" stroke-width="1.5" onclick="jumpToDeckFromAnalytics('${escapeHtmlSafe(b.subdeck)}')">
          <title>${escapeHtmlSafe(b.subdeck.toUpperCase())}: ${b.percent}% avaliado (${b.known} conhecidos, ${b.gaps} gaps)</title>
        </circle>`;
      }).join("");

      return `<div class="ana-svg-stage">
        <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Curva de decaimento de domínio léxico 01K a 10K">
          ${gridLines}
          <polygon points="${areaStr(evalPts)}" fill="color-mix(in oklab, var(--cyan) 16%, transparent)"/>
          <polygon points="${areaStr(knownPts)}" fill="color-mix(in oklab, var(--color-known) 22%, transparent)"/>
          <polyline points="${lineStr(evalPts)}" fill="none" stroke="var(--cyan)" stroke-width="2" stroke-dasharray="4 3"/>
          <polyline points="${lineStr(knownPts)}" fill="none" stroke="var(--color-known)" stroke-width="2.5"/>
          ${dots}
          ${labels}
        </svg>
        <div class="ana-legend-row">
          <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--cyan);"></span>Avaliado (%)</span>
          <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--color-known);"></span>Conhecidos (%)</span>
        </div>
      </div>`;
    }

    function renderAnalyticsMainView(data) {
      const cefrBox = document.getElementById("ana-cefr-bars");
      if (!cefrBox) return;
      const bands = data.cefr_bands || [];
      if (currentAnalyticsView === "radar") {
        cefrBox.innerHTML = renderAnalyticsRadarSvg(bands);
      } else if (currentAnalyticsView === "heatmap") {
        cefrBox.innerHTML = renderAnalyticsHeatmap(bands);
      } else if (currentAnalyticsView === "curve") {
        cefrBox.innerHTML = renderAnalyticsCurveSvg(bands);
      } else {
        cefrBox.innerHTML = bands.map(renderAnalyticsBandRow).join("");
      }
    }

    function renderAnalyticsDonut(tot) {
      const box = document.getElementById("ana-donut-panel");
      if (!box) return;
      const known = tot.known || 0;
      const gaps = tot.gaps || 0;
      const doubts = tot.doubts || 0;
      const sum = Math.max(1, known + gaps + doubts);
      const r = 44, c = 2 * Math.PI * r;
      const segK = (known / sum) * c;
      const segG = (gaps / sum) * c;
      const segD = (doubts / sum) * c;
      const pctK = Math.round((known / sum) * 100);
      const pctG = Math.round((gaps / sum) * 100);
      const pctD = Math.max(0, 100 - pctK - pctG);

      box.innerHTML = `
        <svg width="112" height="112" viewBox="0 0 112 112" role="img" aria-label="Composição da triagem">
          <circle cx="56" cy="56" r="${r}" fill="none" stroke="color-mix(in oklab, var(--text) 9%, transparent)" stroke-width="11"/>
          <circle cx="56" cy="56" r="${r}" fill="none" stroke="var(--color-known)" stroke-width="11" stroke-dasharray="${segK.toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 56 56)"/>
          <circle cx="56" cy="56" r="${r}" fill="none" stroke="var(--color-unknown)" stroke-width="11" stroke-dasharray="${segG.toFixed(1)} ${c.toFixed(1)}" stroke-dashoffset="${(-segK).toFixed(1)}" transform="rotate(-90 56 56)"/>
          <circle cx="56" cy="56" r="${r}" fill="none" stroke="var(--color-doubt)" stroke-width="11" stroke-dasharray="${segD.toFixed(1)} ${c.toFixed(1)}" stroke-dashoffset="${(-(segK + segG)).toFixed(1)}" transform="rotate(-90 56 56)"/>
          <text x="56" y="53" text-anchor="middle" fill="var(--text)" font-size="18" font-weight="800">${tot.mastery_rate || 0}%</text>
          <text x="56" y="68" text-anchor="middle" fill="var(--muted)" font-size="9" font-weight="600">DOMÍNIO</text>
        </svg>
        <div class="ana-donut-legend">
          <div class="ana-donut-row">
            <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--color-known);"></span>Conhecidos</span>
            <strong>${known} <span style="color: var(--muted); font-weight: 500;">(${pctK}%)</span></strong>
          </div>
          <div class="ana-donut-row">
            <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--color-unknown);"></span>Gaps (Anki)</span>
            <strong>${gaps} <span style="color: var(--muted); font-weight: 500;">(${pctG}%)</span></strong>
          </div>
          <div class="ana-donut-row">
            <span class="ana-legend-item"><span class="ana-legend-dot" style="background: var(--color-doubt);"></span>Dúvidas</span>
            <strong>${doubts} <span style="color: var(--muted); font-weight: 500;">(${pctD}%)</span></strong>
          </div>
        </div>`;
    }

    function renderAnalyticsTimeline(tl) {
      const tlBox = document.getElementById("ana-timeline-bars");
      const avgEl = document.getElementById("ana-tl-avg");
      if (!tlBox) return;
      if (!tl.length) {
        if (avgEl) avgEl.textContent = "";
        tlBox.innerHTML = '<span style="font-size: 11px; color: var(--muted);">Sem histórico datado suficiente.</span>';
        return;
      }
      const totalHits = tl.reduce((acc, x) => acc + (x.count || 0), 0);
      if (avgEl) avgEl.textContent = `· Média ${Math.round(totalHits / tl.length)}/dia`;
      const maxC = Math.max(1, ...tl.map(x => x.count));

      if (analyticsTimelineStyle === "line") {
        const w = 320, h = 76, padX = 14, padY = 10, plotH = 44;
        const pts = tl.map((item, i) => {
          const x = padX + (tl.length === 1 ? (w - 2 * padX) / 2 : (i / (tl.length - 1)) * (w - 2 * padX));
          const y = padY + plotH - ((item.count / maxC) * plotH);
          return { x, y, item };
        });
        const poly = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
        const area = `${pts[0].x.toFixed(1)},${(padY + plotH).toFixed(1)} ${poly} ${pts[pts.length - 1].x.toFixed(1)},${(padY + plotH).toFixed(1)}`;
        const dots = pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.2" fill="var(--blue)"><title>${p.item.date}: ${p.item.count} avaliações</title></circle>
          <text x="${p.x.toFixed(1)}" y="${h - 4}" text-anchor="middle" fill="var(--muted)" font-size="8.5" font-family="var(--font-mono)">${p.item.date.slice(8, 10)}/${p.item.date.slice(5, 7)}</text>`).join("");
        tlBox.innerHTML = `<svg viewBox="0 0 ${w} ${h}" style="width: 100%; height: 76px; overflow: visible;">
          <polygon points="${area}" fill="color-mix(in oklab, var(--blue) 18%, transparent)"/>
          <polyline points="${poly}" fill="none" stroke="var(--blue)" stroke-width="2"/>
          ${dots}
        </svg>`;
        return;
      }

      tlBox.innerHTML = tl.map(item => {
        const h = Math.max(10, Math.round((item.count / maxC) * 56));
        return `<div title="${item.date}: ${item.count} avaliações" style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;">
          <div style="width: 100%; max-width: 18px; height: ${h}px; background: var(--blue); border-radius: 3px 3px 0 0; opacity: 0.88;"></div>
          <span style="font-size: 9px; color: var(--muted); font-family: var(--font-mono);">${item.date.slice(8, 10)}/${item.date.slice(5, 7)}</span>
        </div>`;
      }).join("");
    }

    async function loadAnalyticsModule(notifyUser = false) {
      try {
        const res = await fetch('/api/analytics');
        const data = await res.json();
        if (!data || !data.success) return;
        lastAnalyticsData = data;

        const ul = data.user_level || {};
        const tot = data.totals || {};
        document.getElementById('ana-kpi-cefr').textContent = `${ul.code || 'B1'} · ${ul.label || ''}`;
        document.getElementById('ana-kpi-cefr-desc').textContent = ul.desc || '';
        document.getElementById('ana-kpi-mapped').textContent = (tot.mapped_terms || 0).toLocaleString('pt-BR');
        document.getElementById('ana-kpi-senses').textContent = `${(tot.evaluated_senses || 0).toLocaleString('pt-BR')} acepções classificadas`;
        document.getElementById('ana-kpi-mastery').textContent = `${tot.mastery_rate || 0}%`;
        document.getElementById('ana-kpi-breakdown').textContent = `${tot.known || 0} conhecidos · ${tot.gaps || 0} gaps · ${tot.doubts || 0} dúvidas`;
        document.getElementById('ana-kpi-jev').textContent = tot.jev_false_friends || 0;
        document.getElementById('ana-kpi-jev-sub').textContent = `${tot.jev_analyzed || 0} julgamentos em cache Jev`;

        renderAnalyticsMainView(data);
        renderAnalyticsDonut(tot);

        const structBox = document.getElementById('ana-struct-bars');
        if (structBox) structBox.innerHTML = (data.structures_bands || []).map(renderAnalyticsBandRow).join('');

        const posMeta = [
          ['noun', 'Substantivos', 'var(--cyan)'],
          ['verb', 'Verbos', 'var(--blue)'],
          ['adjective', 'Adjetivos', 'var(--purple)'],
          ['other', 'Outros / Listening', 'var(--amber)'],
          ['chunk', 'Chunks / PV', 'var(--color-known)'],
          ['adverb', 'Advérbios', 'var(--dim)']
        ];
        const posBox = document.getElementById('ana-pos-grid');
        if (posBox && data.pos_breakdown) {
          const totalPos = Math.max(1, Object.values(data.pos_breakdown).reduce((a, b) => a + (b || 0), 0));
          posBox.innerHTML = posMeta.map(([k, lbl, color]) => {
            const val = data.pos_breakdown[k] || 0;
            const pct = Math.round((val / totalPos) * 100);
            return `<div class="ana-pos-row">
              <div class="ana-pos-head">
                <span style="color: var(--muted);">${lbl}</span>
                <span><strong style="color: var(--text); font-family: var(--font-mono);">${val}</strong> <span style="color: var(--dim); font-size: 11px;">(${pct}%)</span></span>
              </div>
              <div class="ana-pos-track">
                <div class="ana-pos-fill" style="width: ${pct}%; background: ${color};"></div>
              </div>
            </div>`;
          }).join('');
        }

        renderAnalyticsTimeline(data.daily_timeline || []);

        if (notifyUser) showToast('Telemetria CEFR atualizada.');
      } catch (_) {
        showToast('Erro ao carregar /api/analytics.', false);
      }
    }


    function switchView(mode) {
      document.getElementById("view-focus").style.display = mode === "focus" ? "flex" : "none";
      document.getElementById("view-batch").style.display = mode === "batch" ? "flex" : "none";
      document.getElementById("view-gaps").style.display = mode === "gaps" ? "flex" : "none";

      const dashCard = document.querySelector(".dashboard-progress-card");
      if (dashCard) {
        dashCard.style.display = mode === "gaps" ? "none" : "block";
      }

      document.getElementById("tab-focus").classList.toggle("active", mode === "focus");
      document.getElementById("tab-batch").classList.toggle("active", mode === "batch");
      document.getElementById("tab-gaps").classList.toggle("active", mode === "gaps");

      if (mode === "gaps") {
        loadGapsView();
      }
    }

    // ==========================================
    // ATALHOS DE TECLADO GLOBAIS
    // ==========================================
    function setupKeyboardShortcuts() {
      window.addEventListener("keydown", (e) => {
        if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;

        if (!document.getElementById('view-module-vocab').classList.contains('active')) return;

        const isFocusView = document.getElementById("view-focus").style.display !== "none";
        if (!isFocusView) return;

        const key = e.key.toLowerCase();
        if (key === "1" || key === "c" || e.key === "ArrowRight") {
          e.preventDefault();
          evaluateCurrent("conhecido");
        } else if (key === "2" || key === "n" || e.key === "ArrowLeft") {
          e.preventDefault();
          evaluateCurrent("desconhecido");
        } else if (key === "3" || key === "d" || e.key === "ArrowDown") {
          e.preventDefault();
          evaluateCurrent("duvida");
        } else if (key === "z" || key === "u" || key === "backspace" || (e.ctrlKey && key === "z")) {
          e.preventDefault();
          undoLastEvaluation();
        } else if (key === " " || key === "p") {
          e.preventDefault();
          skipCurrent();
        } else if (key === "k") {
          e.preventDefault();
          markBatchRemainingAsKnown();
        } else if (key === "a") {
          e.preventDefault();
          playCurrentAudio();
        } else if (key === "i") {
          e.preventDefault();
          flagIntruderWord();
        } else if (key === "e") {
          e.preventDefault();
          cycleExample();
        } else if (key === "j") {
          e.preventDefault();
          triggerJevAnalysis();
        }
      });

      // CRAFT: Enable instant :active pseudo-class button-press feedback on iOS Safari
      window.addEventListener("touchstart", () => {}, { passive: true });
    }

    // Dual Theme Switcher (Obsidian Dark + Studio Light)
    function applyLexisTheme(theme) {
      const normalized = (theme === "light" || theme === "paper") ? "light" : "obsidian";
      document.documentElement.setAttribute("data-theme", normalized);
      try { localStorage.setItem("lexis_theme", normalized); } catch (_) {}
      const lbl = document.getElementById("theme-toggle-label");
      if (lbl) lbl.textContent = normalized === "light" ? "Escuro" : "Claro";
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute("content", normalized === "light" ? "#f8fafc" : "#080b10");
    }

    function toggleLexisTheme() {
      const cur = document.documentElement.getAttribute("data-theme") || "obsidian";
      applyLexisTheme(cur === "light" ? "obsidian" : "light");
    }

    (function initLexisTheme() {
      try {
        const saved = localStorage.getItem("lexis_theme");
        if (saved) applyLexisTheme(saved);
      } catch (_) {}
    })();

    (function initLocalLiveReload() {
      const host = window.location.hostname;
      if (host !== "127.0.0.1" && host !== "localhost") return;
      let prev = null;
      setInterval(async () => {
        try {
          const r = await fetch("/api/dev-watch", { cache: "no-store" });
          if (!r.ok) return;
          const cur = await r.json();
          if (!prev) { prev = cur; return; }
          if (cur.html !== prev.html || cur.js !== prev.js) {
            window.location.reload();
            return;
          }
          if (cur.css !== prev.css) {
            const link = document.querySelector('link[href*="/static/css/lexis.css"]');
            if (link) {
              link.href = `/static/css/lexis.css?t=${cur.css}`;
            }
          }
          prev = cur;
        } catch (_) {}
      }, 700);
    })();

  