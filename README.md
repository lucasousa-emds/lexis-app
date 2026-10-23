# ⚡ Lexis App — Ecossistema de Aquisição de Idiomas & Vocabulário Ativo

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/lucasousa-emds/lexis-app)

Plataforma inteligente de alta performance para triagem rápida de vocabulário, comprehensible input ($i+1$), absorção de estruturas nativas (Phrasal Verbs, Collocations, Idioms) e recuperação espaçada no Anki.

---

## 🚀 Como Colocar no Ar no Render (Passo Único)

1. Clique no botão acima **"Deploy to Render"** (ou acesse [dashboard.render.com](https://dashboard.render.com)).
2. Conecte sua conta GitHub e selecione o repositório **`lucasousa-emds/lexis-app`**.
3. O Render lerá o arquivo `render.yaml` automaticamente.
4. Adicione a variável de ambiente:
   * `TYPESAFE_API_KEY`: *(Sua chave da TypeSafe para o Jev)*
5. Clique em **Apply** / **Create Web Service**.
6. Pronto! Sua URL definitiva e permanente estará ativa (ex: `https://lexis-app.onrender.com`).

---

## 🔄 Sincronização com o Anki Desktop

Quando você fizer revisões ou triagens no celular (via link da nuvem), basta sincronizar os novos Gaps para o seu Anki Desktop no computador com um comando:

```bash
python3 "/home/lucas-sousa/anki cards/sync_from_cloud.py" https://SEU-APP.onrender.com
```

O script puxa todas as avaliações da nuvem, consolida o mapa local e injeta os flashcards prontos no baralho `🇬🇧 Inglês::🎯 Meu Estudo Ativo`.
