# Listening Studio — revisão e testes

Revisão de 1 de novembro de 2026. O HTML continua em Vanilla HTML/CSS/JS.

## Correções

- Áudio real com arquivo local, duração e posição reais, velocidade e transcrição SRT/VTT opcional. O tom sintético e os números fictícios foram removidos.
- Ditado: contrações sem confundir `were` com `we're` ou `its` com `it's`; variantes de `he's` e `I'd`; pistas corrigem a primeira palavra divergente; os slots usam os mesmos tokens da validação.
- Estados distintos para acerto sem pistas, conclusão com ajuda e revelação. Revelar não cria cartão. O último trecho apresenta resumo em vez de reiniciar automaticamente.
- Retomada do ditado por fonte, com resposta parcial e resultados, em localStorage. Arquivos locais precisam ser selecionados novamente e suas legendas reimportadas após recarregar a página.
- Pausa ao trocar módulo, submodo, fonte ou ocultar a aba. Reprodução local e YouTube mantêm estados separados. A API do YouTube é carregada sob demanda.
- URL personalizada exige transcrição real; suporta links watch, youtu.be, Shorts, live e embed e rejeita domínios que imitam o YouTube.
- Treinos Altman e Friends ficam indisponíveis até a validação das fontes e dos tempos. Os limites do treino Jobs foram revisados após o relato de corte antecipado. A precisão fina ainda precisa de conferência audiovisual.
- Envios ao Anki Hub conferem HTTP e `success`, têm timeout, ID estável, prevenção de clique duplicado e fila local de reenvio. O texto completo substitui o antigo título truncado. Sucesso significa entrada na fila; a criação do cartão continua pelo fluxo existente.
- Importação ignora leituras atrasadas de arquivos de outra fonte, rejeita tempos inválidos e mantém o conteúdo importado como texto.
- Tab volta a navegar entre controles; Alt+R repete e Alt+H dá pista. Feedback acessível, apenas uma barra mobile, ajustes para telas pequenas e notificações acima da navegação.

## Validação realizada

- 18 cenários automatizados no Chrome, sem erros JavaScript não tratados.
- Reprodução real com WAV e WebM gerados para teste; pausa por trecho, velocidade, busca, transcrição e troca de fonte.
- Interfaces em 320, 390, 767, 768 e 1440 px; capturas de tela e verificação de largura.
- Respostas HTTP 500, erro semântico, falha de rede, confirmação de envio e reenvio pendente com API simulada.
- Cinco testes dos handlers Python reais, incluindo uma requisição HTTP local. Estado e persistência foram substituídos por dados em memória; nenhum cartão ou mapa real foi alterado.
- Comparação confirmou que switchView, evaluateCurrent, onSubdeckChange, syncWithCloud, setupKeyboardShortcuts e undoLastEvaluation permaneceram iguais à versão recebida.

## Como repetir

Com Python 3, Node e Playwright disponíveis no ambiente de testes:

```powershell
python -B tests/test_listening_backend.py
node tests/test_listening_browser.cjs
```

O teste de navegador aceita `LEXIS_PLAYWRIGHT_PATH`, `LEXIS_BROWSER_PATH` e `LEXIS_QA_OUTPUT` para escolher a instalação do Playwright, o executável do navegador e a pasta dos resultados. Por padrão, os resultados vão para a pasta temporária `lexis-listening-qa`. O aplicativo não usa Playwright em produção.

## Limites e próximas melhorias

- A tentativa real de carregar o YouTube não ficou pronta dentro de 15 segundos no ambiente de teste. Os comandos da integração foram testados com player simulado e conferidos com a [referência oficial da API](https://developers.google.com/youtube/iframe_api_reference). Reprodução externa e sincronização dos trechos Jobs não estão confirmadas.
- Celular físico, teclado virtual, Safari/iOS e codecs de aparelhos diferentes ainda precisam de teste. As larguras mobile foram verificadas em Chrome desktop.
- Não foram disparados sync com nuvem ou injeção real no Anki para testar a interface. Esses fluxos foram preservados, mas não validados de ponta a ponta nesta revisão.
- Próxima evolução pedagógica sugerida: tentativa de escuta integral sem pistas, ajuda progressiva e revisão apenas dos trechos difíceis. Separar a métrica de compreensão auditiva da de ortografia.
- Próxima evolução dos cartões: guardar origem e tempos do trecho e anexar seu áudio. O endpoint atual preserva a frase, mas ainda não guarda esses metadados nem recorta o áudio.
- A retomada é local ao navegador. Sincronização da sessão entre dispositivos exigiria integração própria com o backend.


## Correção do corte antecipado no treino Jobs

O primeiro trecho encerrava em 28,2 s, antes de a fala cobrada terminar. Os limites de referência passaram para 25,8–30,1 s, 30,1–35,2 s e 37,3–41,2 s. São referências ajustáveis; a precisão fina não foi confirmada por reprodução audiovisual neste ambiente. A transcrição esperada da primeira frase usa 'for your commencement', de acordo com a fonte oficial da Stanford: https://news.stanford.edu/stories/2005/06/youve-got-find-love-jobs-says .

O botão 'Ouvir mais 2s' amplia o fim do trecho e reproduz a continuação com pequena sobreposição, sem apagar a resposta ou marcar uso de pista. 'Ajustar sincronização do trecho' permite editar início e fim e restaurar os valores de referência. Os ajustes ficam salvos por fonte e trecho. A sessão do preset Jobs usa uma chave estável com migração da chave anterior, mantendo resposta, índice e resultados.

Dois cenários de regressão adicionais verificam o antigo corte de 28,2 s, continuação, resposta preservada, migração, validação dos limites, repetição, persistência e isolamento entre trechos. O backend permanece inalterado.

