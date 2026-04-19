import os, ssl, json, urllib.request, urllib.parse
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

NOCO     = os.environ.get("NOCO_URL", "https://nocodb.papelariaunicornio.com.br/api/v1")
NOCO_TOK = os.environ["NOCO_TOKEN"]
PROJ     = os.environ.get("NOCO_PROJ", "ph9sbcj59aj2l9a")

T_RASTREIO = "mpncar4qj9wvbdx"
T_ASSINA   = "mhjmwzwka27yq95"
T_VENDAS   = "mqf0y9wzfb2ln47"

_ctx = ssl.create_default_context()


def noco_get(table_id, params):
    url = f"{NOCO}/db/data/noco/{PROJ}/{table_id}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "xc-token": NOCO_TOK,
        "User-Agent": "rastreios-pu/1.0",
    })
    with urllib.request.urlopen(req, context=_ctx, timeout=15) as r:
        return json.loads(r.read())


def digits_only(cpf: str) -> str:
    return "".join(c for c in cpf if c.isdigit())


def format_cpf(digits: str) -> str:
    d = digits
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/buscar", methods=["POST"])
def buscar():
    body = request.get_json(silent=True) or {}
    cpf_digits = digits_only(body.get("cpf", ""))
    if len(cpf_digits) != 11:
        return jsonify({"erro": "CPF inválido. Informe 11 dígitos."}), 400

    cpf_fmt = format_cpf(cpf_digits)
    cutoff_dt = datetime.now() - timedelta(days=90)
    cutoff    = cutoff_dt.strftime("%Y-%m-%d")
    cutoff_br = cutoff_dt.strftime("%d/%m/%Y")

    # --- guru_assinaturas ---
    assinatura = None
    email_cliente = None
    try:
        d = noco_get(T_ASSINA, {
            "where": f"(doc,eq,{cpf_digits})",
            "limit": 1,
            "sort": "-started_at",
            "fields": "last_status,next_cycle_at,cycle_end_date,started_at,email",
        })
        if d.get("list"):
            assinatura = d["list"][0]
            email_cliente = assinatura.pop("email", None)
    except Exception:
        pass

    # --- guru_vendas: most recent confirmed purchase ---
    ultima_venda = None
    try:
        d = noco_get(T_VENDAS, {
            "where": f"(doc,eq,{cpf_digits})",
            "limit": 1,
            "sort": "-confirmed_at",
            "fields": "oferta_nome,confirmed_at,status,email",
        })
        if d.get("list"):
            ultima_venda = d["list"][0]
            if not email_cliente:
                email_cliente = ultima_venda.pop("email", None)
            else:
                ultima_venda.pop("email", None)
    except Exception:
        pass

    # --- rastreio_pedidos: try formatted CPF, then digits, then email ---
    pedidos = []
    search_vals = [("cpf_cliente", cpf_fmt), ("cpf_cliente", cpf_digits)]
    if email_cliente:
        search_vals.append(("email_cliente", email_cliente))

    for field, val in search_vals:
        try:
            d = noco_get(T_RASTREIO, {
                "where": f"({field},eq,{val})",
                "limit": 50,
                "sort": "-data_pedido",
                "fields": "Id,id_venda_tiny,numero_ecommerce,data_pedido,dt_postagem,CreatedAt,forma_envio,forma_frete,codigo_rastreio,url_rastreio",
            })
            if d.get("list"):
                pedidos = d["list"]
                break
        except Exception:
            pass

    pedidos = [p for p in pedidos if (p.get("data_pedido") or "") >= cutoff]

    return jsonify({
        "pedidos": pedidos,
        "assinatura": assinatura,
        "ultima_venda": ultima_venda,
        "cutoff_br": cutoff_br,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
