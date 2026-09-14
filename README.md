# Robo de passagens CNF <-> MCO

Monitora automaticamente o preco das passagens Confins (CNF) -> Orlando (MCO)
para as combinacoes de data em `config.json` (busca ida e volta em separado
via Google Flights/SerpApi e combina localmente), e avisa no Telegram quando
o preco de alguma combinacao mudar. Roda sozinho via GitHub Actions, 1x por
dia (meio-dia UTC, ~9h no horario de Brasilia).

## Configuracao (uma vez so)

1. **SerpApi (dados do Google Flights, plano gratuito: 250 buscas/mes)**
   - Crie uma conta em https://serpapi.com/users/sign_up (nao pede cartao pro
     plano free)
   - Depois de logar, sua chave fica em https://serpapi.com/manage-api-key
   - Copie essa chave — e o `SERPAPI_KEY`

2. **Telegram (notificacao, gratis)**
   - Fale com `@BotFather` no Telegram, crie um bot, copie o `token`
   - Mande qualquer mensagem para o bot recem-criado
   - Pegue o seu `chat_id` acessando (trocando `<TOKEN>` pelo token do bot):
     `https://api.telegram.org/bot<TOKEN>/getUpdates`

3. **Cadastrar os secrets no GitHub**
   Repositorio -> Settings -> Secrets and variables -> Actions -> New repository secret:
   - `SERPAPI_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

4. Rode manualmente uma vez pela aba **Actions -> Flight price watch -> Run workflow**
   para receber a primeira mensagem com os precos atuais.

## Mudar rotas ou datas

Edite `config.json`. Cada combinacao de `departure_dates` x `return_dates` e
calculada (preco de ida + preco de volta); a melhor (menor preco, desempate
por menor duracao total de voo) e sempre destacada nas notificacoes.

## Rodar localmente (teste)

```bash
pip install -r requirements.txt
export SERPAPI_KEY=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python scripts/search_flights.py
```

## Sobre a cota gratuita

Cada checagem usa 5 buscas (2 datas de ida + 3 datas de volta, combinadas
localmente para as 6 combinacoes) — 1x/dia da uns 150 buscas/mes, dentro do
plano gratis de 250/mes da SerpApi, com folga para rodar manualmente quando
quiser.

## Observacao sobre o preco

O preco de cada combinacao e a soma dos dois voos separados (ida + volta),
nao uma tarifa "round trip" oficial do Google Flights — normalmente e um bom
proxy do custo real, mas o preco exato pode variar um pouco na hora de
comprar. Use a notificacao para saber quando vale a pena checar o Google
Flights direto e fechar a compra.
