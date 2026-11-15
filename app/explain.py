"""Explanations grounded only in engine outputs.

Default: deterministic rule-based templates (EN/ES), labeled as such.
Optional: if OBSERVAIR_AI=1 and Anthropic credentials are configured, Claude
rephrases the SAME facts. It is told not to add readings, rates, product
restrictions, or override blocking conditions. Any failure falls back to the
rule-based text. Credentials are read server-side only and never sent to the browser."""
import json
import os
from datetime import datetime

from app import catalog, demo_data

S = {
    "en": {
        "rule_based": "Rule-based explanation (generated from engine results)",
        "ai": "AI-phrased explanation (Claude) - rephrases the engine facts listed below",
        "status": {"GO": "Go", "CAUTION": "Caution", "STOP": "Stop", "INSUFFICIENT_DATA": "Insufficient data"},
        "hold_title": "Why is {f} on hold?", "hold_ok_title": "Why is {f} not on hold?",
        "hold_none": "{f} has no hold at {t}. No configured weather flags were detected - that is not a guarantee of safety. Recheck on site before starting.",
        "hold_lead": "{f} is {s} at {t}.",
        "ground": "A 5 ft station alone would say {g}: {gr}",
        "blind": "The 30 ft sensor is what changes the decision.",
        "next_go": "Next simulated slot without blocking flags: {n}.",
        "next_none": "No slot without blocking flags appears in the scenario horizon.",
        "order_title": "Why this job order?",
        "order_same": "The request order {d} is already the best of {n} sequences evaluated.",
        "order_lead": "Evaluated {n} possible sequences. Proposed order: {c}. Request order: {d}.",
        "order_gain": "The proposed order schedules {cs} of {tot} jobs before their deadlines; the request order schedules {ds}.",
        "order_lost": "In the request order, {j} would not fit: {why}.",
        "order_job": "{j} ({f}): {st}-{en}.",
        "order_unsched": "{j} ({f}) stays unscheduled: {why}.",
        "conditional": "These are conditional estimates from simulated data. Confirm fresh local readings before each start.",
        "rain_title": "Can {j} finish before the forecast rain?",
        "rain_ok": "Yes, in this simulated plan: the last pass ends at {e}. {note}",
        "rain_unknown": "The rain check is incomplete: {note}",
        "rain_fail": "Not with a suitable window before the deadline. {note}",
        "rain_unsched": "{j} is not scheduled, so there is no finish time to check against the forecast.",
        "rain_forecast": "Forecast rain is simulated and uncertain; probability is shown, not certainty.",
        "eq_title": "Why is this equipment configuration only a candidate?",
        "eq_conflict": "{u} has unresolved conflicts for {j}:",
        "eq_candidate": "{u} has no configuration conflicts for {j}, but it remains a candidate:",
        "eq_always": "No nozzle or vehicle change can clear a weather Stop such as an inversion.",
        "eq_unverified": "Nozzle droplet data is not verified in this build, so no nozzle is recommended.",
        "nb_title": "Which neighboring area needs attention?",
        "nb_none": "No marked sensitive area is within the attention radius of {f}.",
        "nb_item": "{n}, {d} ft to the {b}: {why}",
        "nb_toward": "air at {h} ft moves toward it (wind from {fr}°, moving toward {to}°)",
        "nb_calm": "wind is near calm, so direction is unreliable",
        "nb_near": "nearby, but air is not moving toward it now",
        "nb_block": " A user-entered constraint holds application in this case.",
        "nb_disclaimer": "This is a wind-direction and distance attention check, not an exposure or deposition prediction.",
        "miss_title": "What information is missing?",
        "miss_none": "Nothing required is missing for {f} at this time.",
        "miss_sensor": "{f} has no paired-height sensor within coverage, so inversions cannot be detected there.",
    },
    "es": {
        "rule_based": "Explicación basada en reglas (generada a partir de los resultados del motor)",
        "ai": "Explicación redactada por IA (Claude) - reformula los datos del motor que se listan abajo",
        "status": {"GO": "Adelante", "CAUTION": "Precaución", "STOP": "Alto", "INSUFFICIENT_DATA": "Datos insuficientes"},
        "hold_title": "¿Por qué {f} está en espera?", "hold_ok_title": "¿Por qué {f} no está en espera?",
        "hold_none": "{f} no tiene espera a las {t}. No se detectaron alertas meteorológicas configuradas; eso no garantiza seguridad. Verifique en el sitio antes de empezar.",
        "hold_lead": "{f} está en {s} a las {t}.",
        "ground": "Una estación a 5 pies por sí sola diría {g}: {gr}",
        "blind": "El sensor a 30 pies es lo que cambia la decisión.",
        "next_go": "Próximo intervalo simulado sin alertas bloqueantes: {n}.",
        "next_none": "No aparece ningún intervalo sin alertas bloqueantes en el horizonte del escenario.",
        "order_title": "¿Por qué este orden de trabajos?",
        "order_same": "El orden solicitado {d} ya es el mejor de las {n} secuencias evaluadas.",
        "order_lead": "Se evaluaron {n} secuencias posibles. Orden propuesto: {c}. Orden solicitado: {d}.",
        "order_gain": "El orden propuesto programa {cs} de {tot} trabajos antes de su fecha límite; el orden solicitado programa {ds}.",
        "order_lost": "En el orden solicitado, {j} no cabría: {why}.",
        "order_job": "{j} ({f}): {st}-{en}.",
        "order_unsched": "{j} ({f}) queda sin programar: {why}.",
        "conditional": "Son estimaciones condicionales con datos simulados. Confirme lecturas locales recientes antes de cada inicio.",
        "rain_title": "¿Puede {j} terminar antes de la lluvia pronosticada?",
        "rain_ok": "Sí, en este plan simulado: la última pasada termina a las {e}. {note}",
        "rain_unknown": "La verificación de lluvia está incompleta: {note}",
        "rain_fail": "No hay una ventana adecuada antes de la fecha límite. {note}",
        "rain_unsched": "{j} no está programado, así que no hay hora de término para comparar con el pronóstico.",
        "rain_forecast": "La lluvia pronosticada es simulada e incierta; se muestra probabilidad, no certeza.",
        "eq_title": "¿Por qué esta configuración de equipo es solo una candidata?",
        "eq_conflict": "{u} tiene conflictos sin resolver para {j}:",
        "eq_candidate": "{u} no tiene conflictos de configuración para {j}, pero sigue siendo candidata:",
        "eq_always": "Ningún cambio de boquilla o vehículo puede anular un Alto meteorológico como una inversión.",
        "eq_unverified": "Los datos de tamaño de gota no están verificados en esta versión, así que no se recomienda ninguna boquilla.",
        "nb_title": "¿Qué área vecina requiere atención?",
        "nb_none": "Ninguna área sensible marcada está dentro del radio de atención de {f}.",
        "nb_item": "{n}, a {d} pies hacia el {b}: {why}",
        "nb_toward": "el aire a {h} pies se mueve hacia ella (viento desde {fr}°, hacia {to}°)",
        "nb_calm": "el viento está casi en calma, así que la dirección no es confiable",
        "nb_near": "está cerca, pero el aire no se mueve hacia ella ahora",
        "nb_block": " Una restricción ingresada por el usuario detiene la aplicación en este caso.",
        "nb_disclaimer": "Es una verificación de atención por dirección del viento y distancia, no una predicción de exposición o depósito.",
        "miss_title": "¿Qué información falta?",
        "miss_none": "No falta nada requerido para {f} en este momento.",
        "miss_sensor": "{f} no tiene un sensor de dos alturas dentro de cobertura, así que no se pueden detectar inversiones allí.",
    },
}
COMPASS = {"en": ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"],
           "es": ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]}


def _hm(iso):
    return datetime.fromisoformat(iso).strftime("%a %H:%M") if iso else "-"


def _compass(deg, lang):
    return COMPASS[lang][int(((deg % 360) + 22.5) // 45) % 8]


def _out(topic, lang, title, lines, facts):
    return {"topic": topic, "lang": lang, "mode": "rule_based", "label": S[lang]["rule_based"],
            "title": title, "lines": [l for l in lines if l], "facts": facts}


def hold(assessment, field, timeline, lang="en"):
    L = S[lang]
    f = field["name"]
    st = assessment["status"]
    t = _hm(assessment["time"])
    if st == "GO":
        return _out("hold", lang, L["hold_ok_title"].format(f=f), [L["hold_none"].format(f=f, t=t)],
                    {"status": st, "time": assessment["time"]})
    lines = [L["hold_lead"].format(f=f, s=L["status"][st], t=t)]
    flagged = [c for c in assessment["checks"] if c["status"] not in ("GO",)]
    lines += [f"{c['label']}: {c['measured']} ({c['threshold']}). {c['reason']}" for c in flagged]
    g = assessment["ground_only"]
    lines.append(L["ground"].format(g=L["status"][g["status"]], gr=g["reason"]))
    if assessment.get("blind_spot"):
        lines.append(L["blind"])
    nxt = next((s for s in timeline if s["time"] > assessment["time"] and s["suitable"]), None)
    lines.append(L["next_go"].format(n=_hm(nxt["time"])) if nxt else L["next_none"])
    return _out("hold", lang, L["hold_title"].format(f=f), lines,
                {"status": st, "checks": [{k: c[k] for k in ("label", "status", "measured", "threshold", "threshold_source")} for c in flagged],
                 "ground_only": g, "observed_at": assessment["provenance"]["observed_at"], "data_kind": assessment["provenance"]["kind"]})


def order(plan, jobs, lang="en"):
    L = S[lang]
    jmap = {j["id"]: j for j in jobs}
    name = lambda jid: f"{jid}"
    fld = lambda jid: demo_data.field(jmap[jid]["field_id"])["name"]
    c, d = plan["chosen"], plan["default"]
    arrow = lambda o: " → ".join(o)
    lines = []
    if c["order"] == d["order"] or (c["scheduled"] == d["scheduled"] and c["weighted_finish_min"] == d["weighted_finish_min"]):
        lines.append(L["order_same"].format(d=arrow(d["order"]), n=plan["sequences_evaluated"]))
    else:
        lines.append(L["order_lead"].format(n=plan["sequences_evaluated"], c=arrow(c["order"]), d=arrow(d["order"])))
        lines.append(L["order_gain"].format(cs=len(c["scheduled"]), ds=len(d["scheduled"]), tot=len(c["order"])))
        for jid in d["unscheduled"]:
            if jid in c["scheduled"]:
                why = d["jobs"][jid]["reason"]
                from app.scheduler import CAUSE_LABEL
                lines.append(L["order_lost"].format(j=jid, why=CAUSE_LABEL.get(why, why)))
    from app.scheduler import CAUSE_LABEL
    for r in plan["jobs"]:
        if r["scheduled"]:
            lines.append(L["order_job"].format(j=r["job_id"], f=fld(r["job_id"]), st=_hm(r["start"]), en=_hm(r["end"])))
        else:
            lines.append(L["order_unsched"].format(j=r["job_id"], f=fld(r["job_id"]),
                                                   why="; ".join(r.get("details") or [CAUSE_LABEL.get(r["reason_code"], r["reason_code"])])))
    lines.append(L["conditional"])
    return _out("order", lang, L["order_title"], lines,
                {"chosen": c, "default": d, "sequences_evaluated": plan["sequences_evaluated"], "objective": plan["objective"]})


def rain(plan, job, lang="en"):
    L = S[lang]
    r = next((x for x in plan["jobs"] if x["job_id"] == job["id"]), None)
    title = L["rain_title"].format(j=job["id"])
    prod = catalog.PRODUCTS.get(job.get("product_id"))
    hours = prod["constraints"]["rainfast_h"] if prod else None
    if not r or not r["scheduled"]:
        lines = [L["rain_unsched"].format(j=job["id"])]
        if r and r.get("reason_code") == "rain":
            lines.append(L["rain_fail"].format(note="; ".join(r.get("details", []))))
    elif r["rain_ok"] is None:
        lines = [L["rain_unknown"].format(note=r["rain_note"])]
    else:
        lines = [L["rain_ok"].format(e=_hm(r["end"]), note=r["rain_note"])]
    if hours:
        lines.append(f"{'Rain-free interval' if lang == 'en' else 'Intervalo sin lluvia'}: {hours['value'] if hours['value'] is not None else '?'} h - {hours['source']}.")
    lines.append(L["rain_forecast"])
    return _out("rain", lang, title, lines, {"result": r, "rainfast": hours})


def equipment_why(ev, job, lang="en"):
    L = S[lang]
    u = ev["unit"]["name"]
    lines = [(L["eq_conflict"] if not ev["compatible"] else L["eq_candidate"]).format(u=u, j=job["id"])]
    for i in ev["issues"]:
        if i["severity"] in ("block", "warn"):
            lines.append(f"• {i['message']}" + (f" [{i['source']}]" if i.get("source") else ""))
    lines.append(L["eq_unverified"])
    lines.append(L["eq_always"])
    return _out("equipment", lang, L["eq_title"], lines, {"issues": ev["issues"], "estimate": ev["estimate"]})


def neighbors(assessment, field, lang="en"):
    L = S[lang]
    nb = assessment["neighbors"]
    if not nb:
        return _out("neighbors", lang, L["nb_title"], [L["nb_none"].format(f=field["name"])], {"neighbors": []})
    lines = []
    for n in nb:
        if not n["direction_reliable"]:
            why = L["nb_calm"]
        else:
            hits = [v for v in n["downwind"].values() if v and v["toward_area"]]
            why = "; ".join(L["nb_toward"].format(h=v["height_ft"], fr=int(v["from_deg"]), to=int(v["toward_deg"])) for v in hits) if hits else L["nb_near"]
        lines.append(L["nb_item"].format(n=n["name"], d=n["distance_ft"], b=_compass(n["bearing_deg"], lang), why=why) + (L["nb_block"] if n["blocking"] else ""))
    lines.append(L["nb_disclaimer"])
    return _out("neighbors", lang, L["nb_title"], lines, {"neighbors": nb})


def missing(assessment, field, ev, job, lang="en"):
    L = S[lang]
    lines = []
    if not field["sensor_id"]:
        lines.append(L["miss_sensor"].format(f=field["name"]))
    for c in assessment["checks"]:
        if c["status"] == "INSUFFICIENT_DATA":
            lines.append(c["measured"])
        if c["id"] == "product_wind" and "Unknown" in c["threshold"]:
            lines.append(c["reason"])
    if ev:
        for i in ev["issues"]:
            if i["code"] in ("method_unknown", "droplet_req_unknown", "droplet_class_missing", "droplet_unverifiable"):
                lines.append(i["message"])
    if job:
        prod = catalog.PRODUCTS.get(job.get("product_id"))
        if prod and prod["constraints"]["rainfast_h"]["value"] is None:
            lines.append("Rain-free interval not entered - rain check incomplete." if lang == "en" else
                         "Intervalo sin lluvia no ingresado - verificación de lluvia incompleta.")
    lines.append("Nozzle droplet charts (pressure-dependent classes) are not loaded in this build." if lang == "en" else
                 "Las tablas de gota de las boquillas (clases según presión) no están cargadas en esta versión.")
    if len(lines) == 1:
        lines.insert(0, L["miss_none"].format(f=field["name"]))
    return _out("missing", lang, L["miss_title"], lines, {})


# ---------------------------------------------------------------- optional AI
SYSTEM = ("You rephrase decision-support explanations for farm spray applicators and PCAs. "
          "Use ONLY the facts provided. Do not add readings, numbers, chemical rates, product restrictions, "
          "or safety claims that are not in the facts. Never soften or override a Stop or Insufficient-data status. "
          "Say that Go means no configured flags were detected, not guaranteed safety. Keep it under 120 words. "
          "Write in {lang}. Plain text, short sentences.")


def ai_available():
    if (os.environ.get("OBSERVAIR_AI") or os.environ.get("CANOPYGUARD_AI")) != "1":  # legacy name still accepted
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def maybe_ai(result: dict):
    """Rephrase a rule-based result with Claude when enabled; otherwise return it unchanged."""
    if not ai_available():
        return result
    import anthropic
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=1024,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=SYSTEM.format(lang="Spanish" if result["lang"] == "es" else "English"),
            messages=[{"role": "user", "content": json.dumps({"question": result["title"], "engine_lines": result["lines"],
                                                               "facts": result["facts"]}, default=str)}],
        )
        if resp.stop_reason == "refusal":
            return result
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            return result
        return {**result, "mode": "ai", "label": S[result["lang"]]["ai"], "ai_text": text}
    except Exception as e:  # network, auth, rate limit: fall back, never block
        return {**result, "ai_error": type(e).__name__}
