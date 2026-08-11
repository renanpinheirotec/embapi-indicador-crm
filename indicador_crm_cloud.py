#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Versão CLOUD do Indicador CRM (SMBOT) da Embapi — roda numa rotina do Claude (dia 01).
Puxa o SMBOT com o token (env SMBOT_TOKEN), gera o painel em HTML (arquivo).
Sem Slack. Mês de referência = mês anterior (ou env REF_MONTH='AAAA-MM').

Uso:  SMBOT_TOKEN="<jwt>" python3 indicador_crm_cloud.py
Saída: indicador_crm_<AAAA-MM>.html  (no diretório atual)
Dep:   pip install requests
"""
import os, sys, calendar, datetime as dt
from collections import defaultdict
import requests

BASE = "https://smsolucoesdigital.com.br"
BOARD_ID = os.environ.get("BOARD_ID", "8273")
TOKEN = os.environ.get("SMBOT_TOKEN", "")
YELLOW = "#fff833"
LIST_EFETIVADO = 44302
LISTS = [44298, 44299, 44300, 44301, 44302, 44306]
LIST_NAMES = {44298: "LEAD", 44299: "Em Contato", 44300: "Lead Qualificado",
              44301: "Orçamento Enviado", 44302: "Pedido Efetivado", 44306: "Lead Desqualificado"}
H = {"Accept": "application/json", "Authorization": TOKEN}
MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


class SmbotError(Exception):
    pass


def _get(path, params=None):
    r = requests.get(f"{BASE}{path}", headers=H, params=params or {}, timeout=60)
    if r.status_code == 401:
        raise SmbotError("401 — token do SMBOT expirou/revogado. Atualize SMBOT_TOKEN na config da rotina.")
    if r.status_code != 200:
        raise SmbotError(f"HTTP {r.status_code} em {path}")
    return r.json()


def month_range(ref):
    if ref:
        y, m = map(int, ref.split("-"))
    else:
        t = dt.date.today().replace(day=1) - dt.timedelta(days=1)
        y, m = t.year, t.month
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


BRT = dt.timezone(dt.timedelta(hours=-3))
# Feriados nacionais de data fixa que podem cair no início do mês (mês, dia)
FERIADOS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}


def primeiro_dia_util(y, m):
    d = dt.date(y, m, 1)
    while d.weekday() >= 5 or (d.month, d.day) in FERIADOS:
        d += dt.timedelta(days=1)
    return d


br = lambda d: d.strftime("%d/%m/%Y")
aux_from = lambda d: f"{d.isoformat()}T03:00:00.000Z"
aux_until = lambda d: f"{(d + dt.timedelta(days=1)).isoformat()}T02:59:59.999Z"


def ms_range(a, b):
    s = int(dt.datetime.fromisoformat(f"{a.isoformat()}T00:00:00-03:00").timestamp() * 1000)
    e = int(dt.datetime.fromisoformat(f"{(b + dt.timedelta(days=1)).isoformat()}T00:00:00-03:00").timestamp() * 1000)
    return s, e


def kpis(a, b):
    p = {"confUsuarioId": 0, "crmBoardId": BOARD_ID, "crmCardAcceptStatus": "WIN",
         "crmCardPriceType": "ALL", "dateFrom": br(a), "dateFromAux": aux_from(a),
         "dateUntil": br(b), "dateUntilAux": aux_until(b)}
    j = _get("/api/crm/dashboards/general/quantity/kpi", p)
    g = lambda k: (j.get(k) or {}).get("countCards", 0)
    return {"criados": g("created"), "aguardando": g("waiting"), "finalizados": g("closed"),
            "perdidos": g("lost")}


def cards(cf="", cu="", clf="", clu=""):
    out, off = [], 0
    while True:
        p = {"boardId": BOARD_ID, "boardTagId": "", "cardId": "", "clientId": "",
             "createdAtFrom": cf, "createdAtUntil": cu, "closedAtFrom": clf, "closedAtUntil": clu,
             "listId": 0, "offset": off, "ownerId": 0, "painelAtendimentoId": "",
             "qualification": "", "title": ""}
        b = _get("/api/crm/cards", p)
        if not b:
            break
        out += b
        if len(b) < 20:
            break
        off += 20
    return out


def list_cards(lid):
    out, off = [], 0
    while True:
        b = _get(f"/api/crm/lists/{lid}/cards", {"offset": off})
        if not b:
            break
        out += b
        if len(b) < 20:
            break
        off += 20
    return out


def atendimentos(cf, cu):
    out, off = [], 0
    while True:
        p = {"atendenteId": -1, "botId": 0, "camposSegmentacao": "[]", "cliente": -1,
             "dataCriacaoDe": cf, "dataCriacaoAte": cu, "departamentoId": -1, "localizacao": "",
             "mes": -1, "motivoId": -1, "offset": off, "orderByFieldName": "CREATE_DATE",
             "orderByFieldOrdenation": "DESC", "origem": "TODOS", "status": "Todos"}
        b = _get("/api/relatorios/atendimentos", p)
        if not b:
            break
        out += b
        if len(b) < 30:
            break
        off += 30
    return out


def ytags(tags):
    return [t["text"] for t in (tags or []) if str(t.get("backgroundColor", "")).lower() == YELLOW]


def get_users():
    j = _get(f"/api/crm/boards/{BOARD_ID}/users")
    arr = j if isinstance(j, list) else j.get("users", [])
    return {u["id"]: (u.get("name") or u.get("nome") or u.get("displayName") or f"#{u['id']}") for u in arr}


def collect(a, b):
    s, e = ms_range(a, b)
    df, du = br(a), br(b)
    k = kpis(a, b)
    created = cards(cf=df, cu=du)
    closed = cards(clf=df, clu=du)
    allc = cards()
    lc, lua = [], {}
    for lid in LISTS:
        cs = list_cards(lid)
        lc += cs
        for c in cs:
            lua[c["id"]] = c.get("listUpdatedAt")
    mc = {c["id"]: ytags((c.get("ticket") or {}).get("tags")) for c in lc}
    mp = {at.get("protocolo"): ytags(at.get("tags"))
          for at in atendimentos(br(dt.date(a.year, 1, 1)), du)}

    def tags_for(c):
        if c["id"] in mc:
            return mc[c["id"]]
        pid = c.get("painelAtendimentoId")
        return mp.get(pid) if pid in mp else None

    def split(cs):
        tag, sem, nc = defaultdict(int), 0, 0
        for c in cs:
            ys = tags_for(c)
            if ys is None:
                nc += 1
            elif not ys:
                sem += 1
            else:
                for y in ys:
                    tag[y] += 1
        return {"total": len(cs), "tag": dict(sorted(tag.items(), key=lambda x: -x[1])),
                "sem": sem, "nc": nc}

    inm = lambda ms: ms is not None and s <= ms < e
    aceitos = [c for c in list_cards(LIST_EFETIVADO) if inm(c.get("listUpdatedAt"))]
    perdidos = [c for c in allc if c.get("accept") == "LOST"
                and (inm(c.get("closedAt")) or (not c.get("closedAt") and inm(lua.get(c["id"]))))]
    motivos = defaultdict(int)
    for c in perdidos:
        rz = (c.get("lostReasonText") or "").strip() or "(sem motivo registrado)"
        motivos[rz] += 1
    perdidos_motivo = dict(sorted(motivos.items(), key=lambda x: -x[1]))

    users = get_users()

    def by_owner(cs):
        o = defaultdict(int)
        for c in cs:
            o[c.get("ownerId") or 0] += 1
        return o
    oc, ofi, oa, op = by_owner(created), by_owner(closed), by_owner(aceitos), by_owner(perdidos)
    por_vendedor = []
    for oid in set(list(oc) + list(ofi) + list(oa) + list(op)):
        nome = "Sem responsável" if not oid else users.get(oid, f"#{oid}")
        por_vendedor.append({"nome": nome, "criados": oc.get(oid, 0), "finalizados": ofi.get(oid, 0),
                             "aceitos": oa.get(oid, 0), "perdidos": op.get(oid, 0)})
    por_vendedor.sort(key=lambda x: -x["criados"])

    return {"kpis": k, "criados": split(created), "finalizados": split(closed),
            "aceitos": split(aceitos), "perdidos": split(perdidos),
            "perdidos_motivo": perdidos_motivo, "por_vendedor": por_vendedor}


def build_html(d, a):
    ref = f"{MESES[a.month]} / {a.year}"
    k, ac = d["kpis"], d["aceitos"]["total"]
    lbl = {"META": "Instagram / Facebook (tráfego pago)", "SITE": "embapi.com.br",
           "PROSPECÇÃO INTERNA": "time interno", "PROSPECÇÃO REPRESENTANTE": "representantes"}
    ors = sorted(set(list(d["criados"]["tag"]) + list(d["finalizados"]["tag"]) +
                     list(d["aceitos"]["tag"]) + list(d["perdidos"]["tag"])),
                 key=lambda t: -d["criados"]["tag"].get(t, 0))
    tot = d["criados"]["total"] or 1
    mx = max([d["criados"]["tag"].get(t, 0) for t in ors] + [1])
    rows = ""
    for t in ors:
        cr = d["criados"]["tag"].get(t, 0); fi = d["finalizados"]["tag"].get(t, 0)
        ae = d["aceitos"]["tag"].get(t, 0); pe = d["perdidos"]["tag"].get(t, 0)
        de = lbl.get(t, "")
        rows += (f'<tr><td class="o"><div class="on"><span class="sw"></span><div><div class="t">{t}</div>'
                 f'{f"<div class=d>{de}</div>" if de else ""}</div></div></td><td>{cr}</td>'
                 f'<td class="{"z" if not fi else ""}">{fi}</td><td class="{"g" if ae else "z"}">{ae}</td>'
                 f'<td class="{"b" if pe else "z"}">{pe}</td>'
                 f'<td class="bc"><span class="bar" style="width:{round(cr/mx*100)}%"></span>'
                 f'<span class="pct">{round(cr/tot*100)}%</span></td></tr>')
    sem = d["criados"]["sem"] + d["criados"]["nc"]
    rows += (f'<tr class="st"><td class="o"><div class="on"><span class="sw" style="background:#8C8071;border:0"></span>'
             f'<div class="t">Sem tag / não classif.</div></div></td><td>{sem}</td>'
             f'<td class="z">{d["finalizados"]["sem"]+d["finalizados"]["nc"]}</td>'
             f'<td class="z">{d["aceitos"]["sem"]+d["aceitos"]["nc"]}</td>'
             f'<td class="z">{d["perdidos"]["sem"]+d["perdidos"]["nc"]}</td><td></td></tr>')
    rows += (f'<tr class="tot"><td class="o"><div class="on"><span class="sw" style="background:transparent;border:0"></span>'
             f'<div class="t">TOTAL</div></div></td><td>{k["criados"]}</td><td>{k["finalizados"]}</td>'
             f'<td>{ac}</td><td>{k["perdidos"]}</td><td></td></tr>')
    mot = d.get("perdidos_motivo", {})
    mtot = sum(mot.values()) or 1
    mmax = max(list(mot.values()) + [1])
    fun = ""
    for rz, n in mot.items():
        fun += (f'<div class="fr flose"><div class="fn">{rz}</div><div class="ft">'
                f'<div class="ff" style="width:{max(n / mmax * 100, 1.5)}%"></div></div>'
                f'<div class="fv">{n} <span style="color:#8C8071;font-weight:600">{round(n / mtot * 100)}%</span></div></div>')
    mp = round(d["criados"]["tag"].get("META", 0) / tot * 100)
    ap = round(d["aceitos"]["tag"].get("PROSPECÇÃO INTERNA", 0) + d["aceitos"]["tag"].get("PROSPECÇÃO REPRESENTANTE", 0))
    vrows = ""
    for v in d.get("por_vendedor", []):
        vrows += (f'<tr><td class="o"><div class="on"><div class="t">{v["nome"]}</div></div></td>'
                  f'<td>{v["criados"]}</td><td class="{"z" if not v["finalizados"] else ""}">{v["finalizados"]}</td>'
                  f'<td class="{"g" if v["aceitos"] else "z"}">{v["aceitos"]}</td>'
                  f'<td class="{"b" if v["perdidos"] else "z"}">{v["perdidos"]}</td></tr>')
    vrows += (f'<tr class="tot"><td class="o"><div class="on"><div class="t">TOTAL</div></div></td>'
              f'<td>{k["criados"]}</td><td>{k["finalizados"]}</td><td>{ac}</td><td>{k["perdidos"]}</td></tr>')
    return f"""<!doctype html><html lang=pt-BR><head><meta charset=utf-8><title>Indicador CRM Embapi — {ref}</title><style>
:root{{--bg:#F4EFE6;--s:#FCFAF5;--s2:#F0E9DC;--ink:#2A2118;--soft:#574B3B;--mut:#8C8071;--ln:#E3D9C9;--lns:#D3C6B0;--ac:#B4681F;--in:#3C6B78;--gd:#2E7D5B;--bd:#B23A2E;--aw:#F3E4D2}}
@media(prefers-color-scheme:dark){{:root{{--bg:#17130E;--s:#201B14;--s2:#29221A;--ink:#F3ECE0;--soft:#CDC1AF;--mut:#9F927D;--ln:#362D22;--lns:#453A2C;--ac:#DB8A3C;--in:#6FA8B6;--gd:#55B487;--bd:#E0685A;--aw:#3A2A18}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.4}}
.w{{width:1280px;margin:0 auto;padding:26px 30px 30px}}
.hd{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid var(--ln);padding-bottom:12px;margin-bottom:14px;gap:20px}}
.eb{{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--mut);font-weight:600;margin:0 0 4px}}
h1{{font-size:25px;margin:0;font-weight:700;letter-spacing:-.02em}}
.pills{{display:flex;gap:8px;flex:none}}
.pill{{display:inline-flex;align-items:center;gap:7px;background:var(--s2);border:1px solid var(--ln);border-radius:999px;padding:5px 12px;font-size:12px;color:var(--soft);white-space:nowrap}}.pill b{{color:var(--ink)}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--gd)}}.sw2{{width:10px;height:10px;border-radius:2px;background:#fff833;display:inline-block}}
.ins{{background:var(--aw);border:1px solid var(--lns);border-radius:10px;padding:9px 16px;font-size:13px;color:var(--soft);margin-bottom:16px}}.ins b{{color:var(--ink)}}.ins .big{{color:var(--ac);font-weight:800;font-size:15px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:start}}
.h2{{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--mut);font-weight:700;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid var(--ln)}}
table{{width:100%;border-collapse:collapse}}
thead th{{text-align:right;font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);font-weight:700;padding:6px 10px;border-bottom:1px solid var(--lns)}}thead th:first-child{{text-align:left}}
tbody td{{padding:7px 10px;border-bottom:1px solid var(--ln);font-variant-numeric:tabular-nums;text-align:right;font-size:13.5px}}
.o{{text-align:left}}.on{{display:flex;align-items:center;gap:8px}}
.sw{{width:10px;height:10px;border-radius:2px;background:#fff833;border:1px solid rgba(0,0,0,.12);flex:none}}.on .t{{font-weight:600;font-size:13.5px}}.on .d{{font-size:10.5px;color:var(--mut)}}
.bc .bar{{display:inline-block;height:6px;border-radius:3px;background:var(--ac);vertical-align:middle;margin-right:8px}}.pct{{font-size:11.5px;color:var(--mut)}}.z{{color:var(--mut)}}.g{{color:var(--gd);font-weight:600}}.b{{color:var(--bd);font-weight:600}}
tr.tot td{{font-weight:700;background:var(--s2)}}tr.st td{{color:var(--mut)}}
.nt{{font-size:11px;color:var(--mut);margin:8px 0 0}}.nt b{{color:var(--soft)}}
.fr{{display:grid;grid-template-columns:158px 1fr 70px;align-items:center;gap:10px;margin-bottom:7px}}.fn{{font-size:11.5px;font-weight:600;color:var(--soft);line-height:1.15}}
.ft{{background:var(--s2);border-radius:5px;height:20px;overflow:hidden;border:1px solid var(--ln)}}.ff{{height:100%;background:var(--bd);opacity:.9}}.fv{{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;font-size:13px}}
</style></head><body><div class="w">
<div class="hd"><div><div class="eb">Indicador mensal · CRM SMBOT · board #{BOARD_ID}</div><h1>Contatos do CRM — Embapi · {ref}</h1></div>
<div class="pills"><span class="pill"><span class="dot"></span> Canal: <b>100% WhatsApp</b></span><span class="pill"><span class="sw2"></span> Origem = <b>tag amarela</b></span></div></div>
<div class="ins"><span class="big">{mp}%</span> dos contatos criados vieram do <b>META</b> (tráfego pago Instagram/Facebook). Dos <b>{ac}</b> aceitos, a <b>Prospecção fez {ap}</b> — converte mais por contato.</div>
<div class="grid2">
<div><div class="h2">Por vendedor</div><table><thead><tr><th>Vendedor</th><th>Criados</th><th>Final.</th><th>Aceitos</th><th>Perdidos</th></tr></thead><tbody>{vrows}</tbody></table></div>
<div><div class="h2">Perdidos — por que foi perdido</div>{fun}<p class="nt">Total oficial de perdidos: <b>{k['perdidos']}</b> · distribuição sobre {mtot} contatos com motivo.</p></div>
</div>
<div class="h2" style="margin-top:16px">Por origem — tags amarelas</div>
<table><thead><tr><th>Origem</th><th>Criados</th><th>Final.</th><th>Aceitos*</th><th>Perdidos*</th><th style="width:24%">% dos criados</th></tr></thead><tbody>{rows}</tbody></table>
<p class="nt">* Aceitos e Perdidos por origem são aproximados (a API não expõe a data exata por card); os totais oficiais estão corretos.</p>
</div></body></html>"""


def main():
    if not TOKEN or "COLE_SEU_TOKEN" in TOKEN:
        print("ERRO: SMBOT_TOKEN não configurado.", file=sys.stderr)
        sys.exit(2)
    ref_env = os.environ.get("REF_MONTH")
    hoje = dt.datetime.now(BRT).date()
    if not ref_env:
        pdu = primeiro_dia_util(hoje.year, hoje.month)
        if hoje != pdu:
            print(f"Hoje ({hoje}) não é o primeiro dia útil do mês (que é {pdu}). Nada a fazer.")
            sys.exit(0)
    a, b = month_range(ref_env)
    d = collect(a, b)
    out = f"indicador_crm_{a.year}-{a.month:02d}.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_html(d, a))
    k = d["kpis"]
    top = " · ".join(f"{t} {n}" for t, n in list(d["criados"]["tag"].items())[:4])
    print(f"OK — {MESES[a.month]}/{a.year} -> {out}")
    print(f"Criados {k['criados']} · Finalizados {k['finalizados']} · "
          f"Aceitos {d['aceitos']['total']} · Perdidos {k['perdidos']} · Aguardando {k['aguardando']}")
    print(f"Origem dos criados: {top}")


if __name__ == "__main__":
    main()
