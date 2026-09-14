# Robo de passagens CNF <-> MCO

Monitora automaticamente o preco das passagens Confins (CNF) -> Orlando (MCO)
para as combinacoes de data em `config.json`, e avisa no Telegram quando o
preco de alguma combinacao mudar. Roda sozinho via GitHub Actions, 2x por dia
(9h e 21h UTC).

## Configuracao (uma vez so)

1. **Criar o repositorio no GitHub** e dar push neste projeto.

2. **Amadeus (dados de voo, gratis ate 2000 chamadas/mes)**
   - Criar conta em https://developers.amadeus.com
   - Criar um app novo -> copiar `API Key` e `API Secret`

3. **Telegram (notificacao, gratis)**
   - Falar com `@BotFather` no Telegram, criar um bot, copiar o `token`
   - Mandar qualquer mensagem para o bot
   - Pegar o seu `chat_id` acessando (com o token do bot):
     `https://api.telegram.org/bot<TOKEN>/getUpdates`

4. **Cadastrar os secrets no GitHub**
   Repositorio -> Settings -> Secrets and variables -> Actions -> New repository secret:
   - `AMADEUS_CLIENT_ID`
   - `AMADEUS_CLIENT_SECRET`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

5. Rodar manualmente uma vez pela aba **Actions -> Flight price watch -> Run workflow**
   para receber a primeira mensagem com os precos atuais.

## Mudar rotas ou datas

Editar `config.json`. Cada combinacao de `departure_dates` x `return_dates` e
checada; a melhor (menor preco, desempate por menor duracao de voo) e sempre
destacada nas notificacoes.

## Rodar localmente (teste)

```bash
pip install -r requirements.txt
export AMADEUS_CLIENT_ID=...
export AMADEUS_CLIENT_SECRET=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python scripts/search_flights.py
```

## Observacao sobre a Amadeus

A API gratuita usa o ambiente de teste (`test.api.amadeus.com`), que pode ter
cobertura menor de voos/tarifas que o ambiente de producao. Para o uso aqui
(poucas checagens por dia) o limite gratuito de 2000 chamadas/mes e mais do
que suficiente.
