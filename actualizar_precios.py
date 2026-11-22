"""
Celu Justo: actualiza prices.json con precios de tiendas chilenas (Google Shopping vía SerpApi).

- Lee la clave desde la variable de entorno SERPAPI_KEY (en GitHub: un "secret").
- Cada ejecución consulta solo POR_DIA modelos, rotando según el día, para no pasar
  de las 250 búsquedas gratis al mes (5 por día = unas 150 al mes con 12 modelos).
- Conserva las ofertas anteriores de los modelos que no toca ese día (cada oferta lleva su fecha).
- Filtra: solo tiendas chilenas de la lista, almacenamiento correcto, precios fuera de rango.
"""
import json, os, sys, unicodedata, urllib.parse, urllib.request
from datetime import date

POR_DIA = 5
ARCHIVO = "prices.json"

# id de la app: búsqueda, palabras obligatorias en el título, almacenamiento, precio de referencia
MODELOS = {
    "a26":   {"q": "Samsung Galaxy A26 5G 128GB",        "debe": ["a26"],          "gb": "128",  "ref": 179900},
    "ef60":  {"q": "Motorola Edge 60 Fusion 256GB",      "debe": ["edge 60 fusion"], "gb": "256", "ref": 199990},
    "rn14p": {"q": "Xiaomi Redmi Note 14 Pro 5G 256GB",  "debe": ["note 14 pro"],  "gb": "256",  "ref": 283990},
    "rn17p": {"q": "Xiaomi Redmi Note 17 Pro 5G 256GB",  "debe": ["note 17 pro"],  "gb": "256",  "ref": 379990},
    "x7p":   {"q": "POCO X7 Pro 256GB",                  "debe": ["x7 pro"],       "gb": "256",  "ref": 409990},
    "s25fe": {"q": "Samsung Galaxy S25 FE 5G 256GB",     "debe": ["s25 fe"],       "gb": "256",  "ref": 448800},
    "x8p":   {"q": "POCO X8 Pro 256GB",                  "debe": ["x8 pro"],       "gb": "256",  "ref": 449990},
    "a57":   {"q": "Samsung Galaxy A57 5G 256GB",        "debe": ["a57"],          "gb": "256",  "ref": 479990},
    "s25u":  {"q": "Samsung Galaxy S25 Ultra 256GB",     "debe": ["s25", "ultra"], "gb": "256",  "ref": 769990},
    "s26u":  {"q": "Samsung Galaxy S26 Ultra 512GB",     "debe": ["s26", "ultra"], "gb": "512",  "ref": 1399990},
    "x17u":  {"q": "Xiaomi 17 Ultra 512GB",              "debe": ["17 ultra"],     "gb": "512",  "ref": 1299990},
    # Solo para traer la foto (su precio viene de MSF Sale, no de este script)
    "p11p":  {"q": "Google Pixel 11 Pro",               "debe": ["pixel 11 pro"], "no": ["xl", "fold"], "solo_img": True},
    "fold8": {"q": "Samsung Galaxy Z Fold 8",           "debe": ["fold", "8"],    "solo_img": True},
    "fx10":  {"q": "Oppo Find X10 Pro Max",              "debe": ["find x10", "max"], "solo_img": True},
    "x500":  {"q": "Vivo X500 Pro Max",                  "debe": ["x500", "max"],  "solo_img": True},
    "x17":   {"q": "Xiaomi 17 512GB",                    "debe": ["xiaomi 17"],    "gb": "512",  "ref": 899990,
              "no": ["ultra", "17t", "17 pro", "17 max"]},
}

# Tiendas chilenas aceptadas (se compara sin tildes ni mayúsculas) y cómo se muestran.
TIENDAS = {
    "falabella": "Falabella", "paris": "Paris", "ripley": "Ripley", "lider": "Lider",
    "hites": "Hites", "abc": "ABC", "entel": "Entel", "movistar": "Movistar", "wom": "WOM",
    "claro": "Claro", "mercadolibre": "MercadoLibre", "mercado libre": "MercadoLibre",
    "pcfactory": "PC Factory", "pc factory": "PC Factory", "la polar": "La Polar",
    "lapolar": "La Polar", "tottus": "Tottus", "sodimac": "Sodimac", "spdigital": "SP Digital",
}
EXCLUIR = ["funda", "case", "protector", "mica", "cargador", "cable", "carcasa", "vidrio",
           "lamina", "soporte", "reacondicionado", "usado", "repuesto", "pantalla de"]
OTROS_GB = ["64", "128", "256", "512", "1tb", "1 tb"]


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()
    return s


def tienda_chilena(nombre):
    n = norm(nombre)
    for clave, bonito in TIENDAS.items():
        if clave in n:
            return bonito
    return None


def almacenamiento_ok(titulo, gb):
    if not gb:
        return True
    t = norm(titulo)
    if gb in t:
        return True
    # si el título nombra otra capacidad distinta, es otra versión
    return not any((o + "gb" in t.replace(" ", "")) for o in OTROS_GB if o != gb)


def buscar(q, key):
    params = {"engine": "google_shopping", "q": q, "gl": "cl", "hl": "es",
              "google_domain": "google.cl", "api_key": key}
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def ofertas_de(data, m, hoy):
    por_tienda = {}
    for it in data.get("shopping_results", []):
        precio, titulo = it.get("extracted_price"), it.get("title", "")
        tienda = tienda_chilena(it.get("source"))
        if not (precio and tienda):
            continue
        t = norm(titulo)
        if not all(p in t for p in m["debe"]) or any(x in t for x in EXCLUIR + m.get("no", [])):
            continue
        if not almacenamiento_ok(titulo, m["gb"]):
            continue
        if not (0.55 * m["ref"] <= precio <= 1.45 * m["ref"]):
            continue
        url = it.get("product_link") or it.get("link") or ""
        if tienda not in por_tienda or precio < por_tienda[tienda]["price"]:
            por_tienda[tienda] = {"store": tienda, "price": int(round(precio)), "url": url, "date": hoy}
    return sorted(por_tienda.values(), key=lambda o: o["price"])


def mejor_img(data, m):
    """Foto del primer resultado que corresponde al modelo (miniatura de Google Shopping)."""
    for it in data.get("shopping_results", []):
        t = norm(it.get("title", ""))
        img = it.get("thumbnail")
        if img and all(p in t for p in m["debe"]) and not any(x in t for x in EXCLUIR + m.get("no", [])) \
                and almacenamiento_ok(it.get("title", ""), m.get("gb")):
            return img
    return None


def main():
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        sys.exit("Falta SERPAPI_KEY")
    hoy = date.today()
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            salida = json.load(f)
    except Exception:
        salida = {"phones": {}}
    salida.setdefault("phones", {})

    ids = sorted(k for k, m in MODELOS.items() if not m.get("solo_img"))
    inicio = (hoy.toordinal() * POR_DIA) % len(ids)
    hoy_ids = [ids[(inicio + i) % len(ids)] for i in range(min(POR_DIA, len(ids)))]
    print("Modelos de hoy:", ", ".join(hoy_ids))

    for pid in hoy_ids:
        m = MODELOS[pid]
        try:
            data = buscar(m["q"], key)
        except Exception as e:
            print(f"  {pid}: error {e}")
            continue
        if data.get("error"):
            print(f"  {pid}: SerpApi dice {data['error']}")
            continue
        lista = ofertas_de(data, m, hoy.isoformat())
        img = mejor_img(data, m)
        print(f"  {pid}: {len(lista)} tiendas, foto {'si' if img else 'no'} -> " + ", ".join(f"{o['store']} {o['price']}" for o in lista))
        entrada = salida["phones"].setdefault(pid, {})
        if lista:  # si no salió nada útil, se conservan las ofertas anteriores
            entrada["offers"] = lista
        if img:
            entrada["img"] = img

    # Fotos que faltan (máx. 4 búsquedas por día y 2 intentos por modelo)
    intentos = salida.setdefault("img_intentos", {})
    faltan = [p for p in MODELOS if p not in hoy_ids
              and not salida["phones"].get(p, {}).get("img") and intentos.get(p, 0) < 2]
    for pid in faltan[:4]:
        m = MODELOS[pid]
        intentos[pid] = intentos.get(pid, 0) + 1
        try:
            data = buscar(m["q"], key)
        except Exception as e:
            print(f"  foto {pid}: error {e}")
            continue
        img = mejor_img(data, m)
        print(f"  foto {pid}: {'si' if img else 'no'}")
        if img:
            salida["phones"].setdefault(pid, {})["img"] = img
    salida["actualizado"] = hoy.isoformat()
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
