"""Robo de busca de passagens: consulta a Amadeus API para todas as combinacoes
de data configuradas, acha a melhor oferta de cada uma, compara com a ultima
checagem salva e avisa no Telegram quando algum preco muda."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "price_history.json"

AMADEUS_BASE = "https://test.api.amadeus.com"


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


def get_token():
    client_id = os.environ["AMADEUS_CLIENT_ID"]
    client_secret = os.environ["AMADEUS_CLIENT_SECRET"]
    r = requests.post(
        f"{AMADEUS_BASE}/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def parse_duration_minutes(iso_duration):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration or "")
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return hours * 60 + minutes


def search_offers(token, cfg, departure_date, return_date):
    r = requests.get(
        f"{AMADEUS_BASE}/v2/shopping/flight-offers",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "originLocationCode": cfg["origin"],
            "destinationLocationCode": cfg["destination"],
            "departureDate": departure_date,
            "returnDate": return_date,
            "adults": cfg.get("adults", 1),
            "travelClass": cfg.get("travel_class", "ECONOMY"),
            "currencyCode": cfg.get("currency", "BRL"),
            "max": 10,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        print(f"  aviso: falha na busca {departure_date}->{return_date}: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return []
    return r.json().get("data", [])


def best_offer(offers):
    best = None
    for o in offers:
        try:
            price = float(o["price"]["grandTotal"])
            currency = o["price"]["currency"]
            total_minutes = sum(parse_duration_minutes(it.get("duration")) for it in o["itineraries"])
            carriers = o.get("validatingAirlineCodes") or []
            carrier = carriers[0] if carriers else "?"
        except (KeyError, ValueError):
            continue
        rank = (price, total_minutes)
        if best is None or rank < best[0]:
            best = (rank, {
                "price": price,
                "currency": currency,
                "duration_minutes": total_minutes,
                "carrier": carrier,
            })
    return best[1] if best else None


def format_duration(minutes):
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}"


def format_offer_line(dep, ret, offer):
    return (
        f"{dep} -> {ret} | R$ {offer['price']:.2f} | "
        f"{format_duration(offer['duration_minutes'])} | {offer['carrier']}"
    )


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

    token = get_token()

    current = {}
    for dep in cfg["departure_dates"]:
        for ret in cfg["return_dates"]:
            key = f"{dep}_{ret}"
            print(f"Buscando {key}...")
            offers = search_offers(token, cfg, dep, ret)
            offer = best_offer(offers)
            if offer:
                offer["last_checked"] = datetime.now(timezone.utc).isoformat()
                offer["departure_date"] = dep
                offer["return_date"] = ret
                current[key] = offer
            else:
                print(f"  nenhuma oferta encontrada para {key}", file=sys.stderr)

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

    overall_best_key = min(current, key=lambda k: (current[k]["price"], current[k]["duration_minutes"]))
    overall_best = current[overall_best_key]

    if is_first_run:
        lines = ["<b>Monitoramento de passagens iniciado</b>", "CNF -> MCO -> CNF", ""]
        for key in sorted(current):
            o = current[key]
            lines.append(format_offer_line(o["departure_date"], o["return_date"], o))
        lines.append("")
        lines.append(f"<b>Melhor combinacao agora:</b> {format_offer_line(overall_best['departure_date'], overall_best['return_date'], overall_best)}")
        send_telegram("\n".join(lines))
    elif changes:
        lines = ["<b>Mudanca de preco detectada</b> (CNF <-> MCO)", ""]
        for key, prev, offer, diff in changes:
            arrow = "queda" if diff < 0 else "alta"
            lines.append(
                f"{offer['departure_date']} -> {offer['return_date']}: "
                f"R$ {prev['price']:.2f} -> R$ {offer['price']:.2f} ({arrow} de R$ {abs(diff):.2f})"
            )
        lines.append("")
        lines.append(f"<b>Melhor combinacao agora:</b> {format_offer_line(overall_best['departure_date'], overall_best['return_date'], overall_best)}")
        send_telegram("\n".join(lines))
    else:
        print("Sem mudancas de preco relevantes, nada a notificar.")

    history["combos"] = current
    history["last_run"] = datetime.now(timezone.utc).isoformat()
    save_history(history)


if __name__ == "__main__":
    main()
