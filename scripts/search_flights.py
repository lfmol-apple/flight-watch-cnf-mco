"""Robo de busca de passagens: consulta o Google Flights via SerpApi para
as pernas de ida e volta configuradas, combina os precos localmente para
achar a melhor combinacao de datas, compara com a ultima checagem salva e
avisa no Telegram quando algum preco muda."""

import itertools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "price_history.json"

SERPAPI_URL = "https://serpapi.com/search"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_history():
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"combos": {}, "last_run": None}


def save_history(history):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, sort_keys=True)


def search_one_way(api_key, origin, destination, date, currency, adults):
    r = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": date,
            "type": 2,  # one way
            "currency": currency,
            "adults": adults,
            "hl": "pt-br",
            "gl": "br",
            "api_key": api_key,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        print(f"  aviso: falha na busca {origin}->{destination} {date}: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    data = r.json()
    candidates = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    best = None
    for item in candidates:
        try:
            price = float(item["price"])
            duration = int(item.get("total_duration") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        flights = item.get("flights") or []
        carrier = flights[0].get("airline") if flights else "?"
        rank = (price, duration)
        if best is None or rank < best[0]:
            best = (rank, {"price": price, "duration_minutes": duration, "carrier": carrier})
    if best is None:
        print(f"  nenhuma oferta encontrada para {origin}->{destination} {date}", file=sys.stderr)
        return None
    return best[1]


def format_duration(minutes):
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}"


def format_brl(value):
    s = f"{value:,.2f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def format_date_br(iso_date):
    y, m, d = iso_date.split("-")
    return f"{d}/{m}"


def ranked_keys(current):
    return sorted(current, key=lambda k: (current[k]["price"], current[k]["duration_minutes"]))


def build_ranking_table(current):
    order = ranked_keys(current)
    best_key = order[0]
    header = f" {'Ida':<5} {'Volta':<5} {'Preco':>12} {'Duracao':>8}  Cia"
    lines = [header, "-" * len(header)]
    for key in order:
        o = current[key]
        mark = "*" if key == best_key else " "
        lines.append(
            f"{mark}{format_date_br(o['departure_date']):<5} {format_date_br(o['return_date']):<5} "
            f"{('R$ ' + format_brl(o['price'])):>12} {format_duration(o['duration_minutes']):>8}  {o['carrier']}"
        )
    return "<pre>" + "\n".join(lines) + "</pre>"


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram nao configurado, pulando notificacao.", file=sys.stderr)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=30,
    )
    if r.status_code >= 400:
        print(f"Falha ao enviar Telegram: {r.status_code} {r.text[:300]}", file=sys.stderr)


def main():
    cfg = load_config()
    history = load_history()
    is_first_run = not history["combos"]

    api_key = os.environ["SERPAPI_KEY"]
    currency = cfg.get("currency", "BRL")
    adults = cfg.get("adults", 1)
    origin = cfg["origin"]
    destination = cfg["destination"]

    outbound_legs = {}
    for dep in cfg["departure_dates"]:
        print(f"Buscando ida {origin}->{destination} {dep}...")
        leg = search_one_way(api_key, origin, destination, dep, currency, adults)
        if leg:
            outbound_legs[dep] = leg

    return_legs = {}
    for ret in cfg["return_dates"]:
        print(f"Buscando volta {destination}->{origin} {ret}...")
        leg = search_one_way(api_key, destination, origin, ret, currency, adults)
        if leg:
            return_legs[ret] = leg

    current = {}
    for dep, ret in itertools.product(cfg["departure_dates"], cfg["return_dates"]):
        out_leg = outbound_legs.get(dep)
        ret_leg = return_legs.get(ret)
        if not out_leg or not ret_leg:
            continue
        key = f"{dep}_{ret}"
        current[key] = {
            "departure_date": dep,
            "return_date": ret,
            "price": out_leg["price"] + ret_leg["price"],
            "duration_minutes": out_leg["duration_minutes"] + ret_leg["duration_minutes"],
            "carrier": f"{out_leg['carrier']} / {ret_leg['carrier']}",
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

    if not current:
        print("Nenhuma oferta encontrada em nenhuma combinacao. Encerrando sem notificar.", file=sys.stderr)
        return

    min_change = cfg.get("min_price_change", 1.0)
    changes = []
    for key, offer in current.items():
        prev = history["combos"].get(key)
        if prev is None:
            continue
        diff = offer["price"] - prev["price"]
        if abs(diff) >= min_change:
            changes.append((key, prev, offer, diff))

    table = build_ranking_table(current)

    if is_first_run:
        lines = [
            "<b>Monitoramento de passagens iniciado</b>",
            f"{origin} -> {destination} -> {origin} (ordenado por preco, * = melhor)",
            "",
            table,
        ]
        send_telegram("\n".join(lines))
    elif changes:
        changes.sort(key=lambda c: (c[2]["departure_date"], c[2]["return_date"]))
        lines = [f"<b>Mudanca de preco detectada</b> ({origin} &lt;-&gt; {destination})", ""]
        for key, prev, offer, diff in changes:
            arrow = "queda" if diff < 0 else "alta"
            lines.append(
                f"{format_date_br(offer['departure_date'])} -> {format_date_br(offer['return_date'])}: "
                f"R$ {format_brl(prev['price'])} -> R$ {format_brl(offer['price'])} ({arrow} de R$ {format_brl(abs(diff))})"
            )
        lines.append("")
        lines.append("Ranking atualizado (ordenado por preco, * = melhor):")
        lines.append(table)
        send_telegram("\n".join(lines))
    else:
        print("Sem mudancas de preco relevantes, nada a notificar.")

    history["combos"] = current
    history["last_run"] = datetime.now(timezone.utc).isoformat()
    save_history(history)


if __name__ == "__main__":
    main()
