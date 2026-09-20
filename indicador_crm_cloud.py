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

# Identidade visual por empresa (fundo branco; verde/vermelho são sinais de aceito/perdido)
BRANDS = {
    "embapi": {"label": "Embapi", "board": 8273, "ac": "#E78700", "dark": "#B4681F",
               "aw": "#FDF0DA", "ink": "#23201C", "s2": "#F6F2EA", "ln": "#ECE6DA", "lns": "#DDD5C6"},
    "newup": {"label": "NEWUP", "board": 8348, "ac": "#810293", "dark": "#3D1068",
              "aw": "#F3E6F7", "ink": "#241033", "s2": "#F5F0F8", "ln": "#EBE3F1", "lns": "#DCCFE7"},
}


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
    lc, lua, pipe_counts = [], {}, {}
    for lid in LISTS:
        cs = list_cards(lid)
        pipe_counts[lid] = len(cs)
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
    efetivado_cards = list_cards(LIST_EFETIVADO)
    aceitos = [c for c in efetivado_cards if inm(c.get("listUpdatedAt"))]

    # Perdidos OFICIAL (por data de perda) via dashboard accept/reasons — soma bate com o KPI "lost".
    qp = {"crmBoardId": BOARD_ID, "dateFrom": df, "dateFromAux": aux_from(a),
          "dateUntil": du, "dateUntilAux": aux_until(b)}

    def lost_reasons(user_id=0):
        p = dict(qp, accept="LOST", confUsuarioId=user_id)
        j = _get("/api/crm/dashboards/accept/reasons", p)
        return j if isinstance(j, list) else []
    perdidos_motivo = {(x.get("name") or "(sem motivo registrado)"): x.get("countCards", 0)
                       for x in lost_reasons(0)}

    users = get_users()

    def by_owner(cs):
        o = defaultdict(int)
        for c in cs:
            o[c.get("ownerId") or 0] += 1
        return o
    oc, ofi, oa = by_owner(created), by_owner(closed), by_owner(aceitos)
    lost_by = {uid: sum(x.get("countCards", 0) for x in lost_reasons(uid)) for uid in users}
    por_vendedor = []
    for oid in set(list(oc) + list(ofi) + list(oa) + list(lost_by)):
        nome = "Sem responsável" if not oid else users.get(oid, f"#{oid}")
        v = {"nome": nome, "criados": oc.get(oid, 0), "finalizados": ofi.get(oid, 0),
             "aceitos": oa.get(oid, 0), "perdidos": lost_by.get(oid, 0)}
        if any(v[x] for x in ("criados", "finalizados", "aceitos", "perdidos")):
            por_vendedor.append(v)
    por_vendedor.sort(key=lambda x: -x["criados"])

    # ---- Blocos padrão PPT: pipeline, comparativo, quantidade geral (só atendente) ----
    NOMES_LISTA = {44298: "Novos (LEAD)", 44299: "Em contato", 44300: "Lead qualificado",
                   44301: "Orçamento enviado", 44302: "Pedido efetivado", 44306: "Lead desqualificado"}
    pipeline = [{"etapa": NOMES_LISTA.get(lid, str(lid)), "qtd": pipe_counts.get(lid, 0)} for lid in LISTS]

    # mês anterior (para comparativo e quantidade geral)
    pa = a.replace(day=1) - dt.timedelta(days=1)
    prev_a, prev_b = pa.replace(day=1), pa
    pdf, pdu = br(prev_a), br(prev_b)
    kprev = kpis(prev_a, prev_b)
    sp, ep = ms_range(prev_a, prev_b)
    inmp = lambda ms: ms is not None and sp <= ms < ep
    aceitos_prev = len([c for c in efetivado_cards if inmp(c.get("listUpdatedAt"))])
    comparativo = {"ant_label": MESES[prev_a.month], "atual_label": MESES[a.month], "linhas": [
        {"etapa": "Contatos criados", "ant": kprev["criados"], "atual": k["criados"]},
        {"etapa": "Finalizados", "ant": kprev["finalizados"], "atual": k["finalizados"]},
        {"etapa": "Aceitos (Pedido Efetivado)", "ant": aceitos_prev, "atual": len(aceitos)},
        {"etapa": "Perdidos", "ant": kprev["perdidos"], "atual": k["perdidos"]},
    ]}

    created_prev = cards(cf=pdf, cu=pdu)
    oc_prev = by_owner(created_prev)
    qg_linhas = []
    for oid in set(list(oc) + list(oc_prev)):
        if not oid:
            continue
        ant, atual = oc_prev.get(oid, 0), oc.get(oid, 0)
        if ant or atual:
            qg_linhas.append({"atendente": users.get(oid, f"#{oid}"), "ant": ant, "atual": atual})
    qg_linhas.sort(key=lambda x: -(x["ant"] + x["atual"]))
    quantidade_geral = {"ant_label": MESES[prev_a.month], "atual_label": MESES[a.month], "linhas": qg_linhas}

    return {"kpis": k, "criados": split(created), "finalizados": split(closed),
            "aceitos": split(aceitos), "perdidos_motivo": perdidos_motivo,
            "por_vendedor": por_vendedor,
            "pipeline": pipeline, "comparativo": comparativo, "quantidade_geral": quantidade_geral}


def build_html(d, a, brand="embapi"):
    bp = BRANDS.get(brand, BRANDS["embapi"])
    ref = f"{MESES[a.month]} / {a.year}" + d.get("ref_extra", "")
    k, ac = d["kpis"], d["aceitos"]["total"]
    lbl = {"META": "Instagram / Facebook (tráfego pago)", "META (INSTA/FACE)": "Instagram / Facebook",
           "PROSPECÇÃO INTERNA": "time interno", "PROSPECÇÃO REPRESENTANTE": "representantes"}
    og = d.get("origem", d["criados"])
    ors = sorted(set(list(og["tag"]) + list(d["finalizados"]["tag"]) +
                     list(d["aceitos"]["tag"])),
                 key=lambda t: -og["tag"].get(t, 0))
    tot = og["total"] or 1
    mx = max([og["tag"].get(t, 0) for t in ors] + [1])
    rows = ""
    for t in ors:
        cr = og["tag"].get(t, 0); fi = d["finalizados"]["tag"].get(t, 0)
        ae = d["aceitos"]["tag"].get(t, 0)
        de = lbl.get(t, "")
        rows += (f'<tr><td class="o"><div class="on"><span class="sw"></span><div><div class="t">{t}</div>'
                 f'{f"<div class=d>{de}</div>" if de else ""}</div></div></td><td>{cr}</td>'
                 f'<td class="{"z" if not fi else ""}">{fi}</td><td class="{"g" if ae else "z"}">{ae}</td>'
                 f'<td class="bc"><span class="bar" style="width:{round(cr/mx*100)}%"></span>'
                 f'<span class="pct">{round(cr/tot*100)}%</span></td></tr>')
    sem = og["sem"] + og["nc"]
    rows += (f'<tr class="st"><td class="o"><div class="on"><span class="sw" style="background:#8C8071;border:0"></span>'
             f'<div class="t">Sem tag / não classif.</div></div></td><td>{sem}</td>'
             f'<td class="z">{d["finalizados"]["sem"]+d["finalizados"]["nc"]}</td>'
             f'<td class="z">{d["aceitos"]["sem"]+d["aceitos"]["nc"]}</td><td></td></tr>')
    ot = d.get("origem_totais", {"c": k["criados"], "f": k["finalizados"], "a": ac})
    rows += (f'<tr class="tot"><td class="o"><div class="on"><span class="sw" style="background:transparent;border:0"></span>'
             f'<div class="t">TOTAL</div></div></td><td>{ot["c"]}</td><td>{ot["f"]}</td>'
             f'<td>{ot["a"]}</td><td></td></tr>')
    mot = d.get("perdidos_motivo", {})
    mtot = sum(mot.values()) or 1
    mmax = max(list(mot.values()) + [1])
    fun = ""
    for rz, n in mot.items():
        fun += (f'<div class="fr flose"><div class="fn">{rz}</div><div class="ft">'
                f'<div class="ff" style="width:{max(n / mmax * 100, 1.5)}%"></div></div>'
                f'<div class="fv">{n} <span style="color:#8C8071;font-weight:600">{round(n / mtot * 100)}%</span></div></div>')
    if d.get("insight_html"):
        insight = d["insight_html"]
    else:
        semc = og["sem"] + og["nc"]
        sem_pct = round(semc / tot * 100)
        _top = list(og["tag"].items())
        _tn, _tv = (_top[0] if _top else ("—", 0))
        _tp = round(_tv / tot * 100)
        if sem_pct >= 40:
            insight = (f'<span class="big">{sem_pct}%</span> dos contatos criados estão <b>sem tag de origem</b>. '
                       f'Entre os marcados, <b>{_tn}</b> lidera ({_tv}).')
        else:
            insight = f'<span class="big">{_tp}%</span> dos contatos criados vieram de <b>{_tn}</b>. Aceitos no mês: <b>{ac}</b>.'
    pnota = d.get("perdidos_nota") or f"Total oficial de perdidos: <b>{k['perdidos']}</b> · distribuição sobre {mtot} contatos com motivo."
    vrows = ""
    for v in d.get("por_vendedor", []):
        vrows += (f'<tr><td class="o"><div class="on"><div class="t">{v["nome"]}</div></div></td>'
                  f'<td>{v["criados"]}</td><td class="{"z" if not v["finalizados"] else ""}">{v["finalizados"]}</td>'
                  f'<td class="{"g" if v["aceitos"] else "z"}">{v["aceitos"]}</td>'
                  f'<td class="{"b" if v["perdidos"] else "z"}">{v["perdidos"]}</td></tr>')
    vrows += (f'<tr class="tot"><td class="o"><div class="on"><div class="t">TOTAL</div></div></td>'
              f'<td>{k["criados"]}</td><td>{k["finalizados"]}</td><td>{ac}</td><td>{k["perdidos"]}</td></tr>')
    anms = d.get("aceitos_nomes", [])
    anames = "".join(f'<span class="ach"><b>{x["nome"]}</b><span class="av">{x["vendedor"]}</span></span>' for x in anms)
    anames_sec = (f'<div class="h2" style="margin-top:28px">Aceitos — o que foi fechado ({len(anms)})</div>'
                  f'<div class="anames">{anames}</div>') if anms else ""

    # ---- Blocos padrão PPT (KPI cards, pipeline, comparativo, quantidade geral) ----
    def _card(lbl, val, cls): return f'<div class="kpi {cls}"><div class="kn">{val}</div><div class="kl">{lbl}</div></div>'
    cards_html = ('<div class="kpis">' + _card("Atendimentos criados", k["criados"], "c-blue")
                  + _card("Finalizados", k["finalizados"], "c-dark") + _card("Aceitos", ac, "c-green")
                  + _card("Perdidos", k["perdidos"], "c-red") + '</div>')
    pipe_html = ""
    pipe = d.get("pipeline")
    if pipe:
        ptot = sum(x["qtd"] for x in pipe) or 1
        prows = "".join(f'<tr><td class="o"><div class="on"><div class="t">{x["etapa"]}</div></div></td>'
                        f'<td>{x["qtd"]}</td><td class="pcell">{x["qtd"]/ptot*100:.1f}%</td></tr>' for x in pipe)
        prows += (f'<tr class="tot"><td class="o"><div class="on"><div class="t">TOTAL</div></div></td>'
                  f'<td>{ptot}</td><td>100,0%</td></tr>')
        pipe_html = (f'<div class="h2" style="margin-top:28px">Pipeline — distribuição por etapa</div>'
                     f'<table><thead><tr><th>Etapa</th><th>Qtd.</th><th style="width:24%">% do pipeline</th></tr></thead>'
                     f'<tbody>{prows}</tbody></table>')
    comp_html = ""
    comp = d.get("comparativo")
    if comp:
        la, lb = comp.get("ant_label", "Mês anterior"), comp.get("atual_label", "Mês atual")
        crows = ""
        for x in comp.get("linhas", []):
            crows += (f'<tr><td class="o"><div class="on"><div class="t">{x["etapa"]}</div></div></td>'
                      f'<td>{x["ant"]}</td><td>{x["atual"]}</td></tr>')
        comp_html = (f'<div class="h2" style="margin-top:28px">Comparativo com o mês anterior</div>'
                     f'<table><thead><tr><th>Etapa</th><th>{la}</th><th>{lb}</th>'
                     f'</tr></thead><tbody>{crows}</tbody></table>')
    qg_html = ""  # tabela "Quantidade geral de atendimentos" removida (redundante com "por vendedor")

    return f"""<!doctype html><html lang=pt-BR><head><meta charset=utf-8><title>Indicador CRM Embapi — {ref}</title><style>
:root{{--bg:#FFFFFF;--s:#FFFFFF;--s2:{bp['s2']};--ink:{bp['ink']};--soft:#5A5348;--mut:#948B7D;--ln:{bp['ln']};--lns:{bp['lns']};--ac:{bp['ac']};--in:{bp['dark']};--gd:#5E8E1E;--bd:#C0392B;--aw:{bp['aw']}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.4}}
.w{{width:1280px;margin:0 auto;padding:26px 30px 30px}}
.hd{{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid var(--ac);padding-bottom:12px;margin-bottom:14px;gap:20px}}
.eb{{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--mut);font-weight:600;margin:0 0 4px}}
h1{{font-size:25px;margin:0;font-weight:700;letter-spacing:-.02em}}
.pills{{display:flex;gap:8px;flex:none}}
.pill{{display:inline-flex;align-items:center;gap:7px;background:var(--s2);border:1px solid var(--ln);border-radius:999px;padding:5px 12px;font-size:12px;color:var(--soft);white-space:nowrap}}.pill b{{color:var(--ink)}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--gd)}}.sw2{{width:10px;height:10px;border-radius:2px;background:#fff833;display:inline-block}}
.ins{{background:var(--aw);border:1px solid var(--lns);border-radius:10px;padding:9px 16px;font-size:13px;color:var(--soft);margin-bottom:16px}}.ins b{{color:var(--ink)}}.ins .big{{color:var(--ac);font-weight:800;font-size:15px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}}
.kpi{{background:var(--s2);border:1px solid var(--ln);border-radius:10px;padding:12px 16px;border-left:5px solid var(--mut)}}
.kpi.c-blue{{border-left-color:#2E6BB8}}.kpi.c-dark{{border-left-color:var(--in)}}.kpi.c-green{{border-left-color:var(--gd)}}.kpi.c-red{{border-left-color:var(--bd)}}
.kpi .kn{{font-size:26px;font-weight:800;letter-spacing:-.02em}}.kpi .kl{{font-size:11.5px;color:var(--mut);font-weight:600;margin-top:2px}}
.pcell{{color:var(--soft);font-weight:600}}
.sub{{font-size:13px;color:var(--soft);margin-top:3px;font-weight:500}}
.twrap{{overflow-x:auto}}.tt{{font-weight:700}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:start}}
.h2{{font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink);font-weight:800;margin:28px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--ac)}}
table{{width:100%;border-collapse:collapse}}
thead th{{text-align:right;font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);font-weight:700;padding:6px 10px;border-bottom:1px solid var(--lns)}}thead th:first-child{{text-align:left}}
tbody td{{padding:7px 10px;border-bottom:1px solid var(--ln);font-variant-numeric:tabular-nums;text-align:right;font-size:13.5px}}
.o{{text-align:left}}.on{{display:flex;align-items:center;gap:8px}}
.sw{{width:10px;height:10px;border-radius:2px;background:#fff833;border:1px solid rgba(0,0,0,.12);flex:none}}.on .t{{font-weight:600;font-size:13.5px}}.on .d{{font-size:10.5px;color:var(--mut)}}
.bc .bar{{display:inline-block;height:6px;border-radius:3px;background:var(--ac);vertical-align:middle;margin-right:8px}}.pct{{font-size:11.5px;color:var(--mut)}}.z{{color:var(--mut)}}.g{{color:var(--gd);font-weight:600}}.b{{color:var(--bd);font-weight:600}}
tr.tot td{{font-weight:700;background:var(--s2)}}tr.st td{{color:var(--mut)}}
.nt{{font-size:11px;color:var(--mut);margin:8px 0 0}}.nt b{{color:var(--soft)}}
.anames{{display:flex;flex-wrap:wrap;gap:8px}}.ach{{background:var(--s2);border:1px solid var(--ln);border-radius:8px;padding:6px 12px;font-size:12.5px;color:var(--soft)}}.ach b{{color:var(--ink);font-weight:600}}.av{{color:var(--ac);font-weight:600;margin-left:6px}}
.fr{{display:grid;grid-template-columns:158px 1fr 70px;align-items:center;gap:10px;margin-bottom:7px}}.fn{{font-size:11.5px;font-weight:600;color:var(--soft);line-height:1.15}}
.ft{{background:var(--s2);border-radius:5px;height:20px;overflow:hidden;border:1px solid var(--ln)}}.ff{{height:100%;background:var(--bd);opacity:.9}}.fv{{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;font-size:13px}}
</style></head><body><div class="w">
<div class="hd"><div><div class="eb">Indicador mensal · CRM SMBOT · board #{bp['board']}</div><h1>Contatos do CRM — {bp['label']} · {ref}</h1><div class="sub">Visão executiva consolidada do CRM</div></div>
<div class="pills"><span class="pill"><span class="dot"></span> Canal: <b>100% WhatsApp</b></span><span class="pill"><span class="sw2"></span> Origem = <b>tag amarela</b></span></div></div>
<div class="ins">{insight}</div>
{cards_html}
{pipe_html}
<div class="grid2">
<div><div class="h2">{d.get("vend_titulo","Por vendedor")}</div><table><thead><tr><th>Vendedor</th><th>Criados</th><th>Final.</th><th>Aceitos</th><th>Perdidos</th></tr></thead><tbody>{vrows}</tbody></table></div>
<div><div class="h2">Perdidos — por que foi perdido</div>{fun}<p class="nt">Total de perdidos: <b>{k['perdidos']}</b> — quebra por motivo direto do CRM (por data de perda).</p></div>
</div>
<div class="h2" style="margin-top:28px">{d.get("origem_titulo","Por origem — tags amarelas")}</div>
<table><thead><tr><th>Origem</th><th>Criados</th><th>Final.</th><th>Aceitos*</th><th style="width:26%">% do total</th></tr></thead><tbody>{rows}</tbody></table>
<p class="nt">{d.get("origem_nota","* Aceitos por origem é aproximado (cards que entraram em Pedido Efetivado). Criados e Finalizados por origem vêm das tags do atendimento.")}</p>
{comp_html}
{anames_sec}
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


def _supa(su, sk, method, path, data=None, ctype=None):
    u = su.rstrip("/") + "/storage/v1/object/relatorio/" + path
    h = {"Authorization": "Bearer " + sk, "apikey": sk}
    if method == "GET":
        return requests.get(u, headers=h, timeout=45)
    h["x-upsert"] = "true"; h["Cache-Control"] = "no-cache, max-age=0"
    if ctype:
        h["Content-Type"] = ctype
    return requests.post(u, headers=h, data=data, timeout=90)


def gerar_semanal():
    """Modo SEMANAL: gera o relatório do MÊS CORRENTE (acumulado) e sobe pra Supabase
    (HTML por mês + índice), que a Central lê. Env: SMBOT_TOKEN, SUPABASE_URL, SUPABASE_KEY."""
    import json
    su, sk = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not TOKEN or "COLE_SEU_TOKEN" in TOKEN:
        print("ERRO: SMBOT_TOKEN não configurado.", file=sys.stderr); sys.exit(2)
    if not su or not sk:
        print("ERRO: SUPABASE_URL/SUPABASE_KEY não configurados.", file=sys.stderr); sys.exit(2)
    ref_env = os.environ.get("REF_MONTH")
    hoje = dt.datetime.now(BRT).date()
    if ref_env:
        a, b = month_range(ref_env)
    else:
        a, b = hoje.replace(day=1), hoje  # mês corrente até hoje (acumulado)
    d = collect(a, b)
    if b.day < calendar.monthrange(a.year, a.month)[1]:
        d["ref_extra"] = f" · parcial até {b.day:02d}/{a.month:02d}"
    html = build_html(d, a)
    mk = f"{a.year}-{a.month:02d}"
    fname = f"indicador_embapi_{mk}.html"
    r = _supa(su, sk, "POST", fname, html.encode("utf-8"), "text/html; charset=utf-8")
    print(f"upload {fname}: HTTP {r.status_code}")
    idx = {"empresa": "Embapi", "meses": []}
    try:
        g = _supa(su, sk, "GET", "indicador_embapi_index.json")
        if g.status_code == 200:
            idx = g.json(); idx.setdefault("meses", [])
    except Exception as ex:
        print("índice atual não lido (ok se 1ª vez):", ex)
    idx["meses"] = [m for m in idx.get("meses", []) if m.get("key") != mk]
    idx["meses"].append({"key": mk, "label": f"{MESES[a.month]}/{a.year}", "file": fname})
    idx["meses"].sort(key=lambda m: m["key"], reverse=True)
    idx["atualizado"] = hoje.isoformat()
    ri = _supa(su, sk, "POST", "indicador_embapi_index.json",
               json.dumps(idx, ensure_ascii=False).encode("utf-8"), "application/json")
    k = d["kpis"]
    print(f"index: HTTP {ri.status_code} — {MESES[a.month]}/{a.year} | Criados {k['criados']} "
          f"Finalizados {k['finalizados']} Aceitos {d['aceitos']['total']} Perdidos {k['perdidos']}")


if __name__ == "__main__":
    if os.environ.get("MODO") == "semanal":
        gerar_semanal()
    else:
        main()
